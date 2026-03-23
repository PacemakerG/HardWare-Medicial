"""
MediGenius — tools/keyword_retriever.py
Lightweight BM25-style keyword retriever built on top of Chroma stored chunks.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from langchain_core.documents import Document

from app.core.logging_config import logger
from app.core.medical_taxonomy import extract_query_terms
from app.tools.vector_store import get_or_create_vectorstore

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}")
_INDEX_LOCK = threading.Lock()
_INDEX_CACHE: Dict[str, "_ScopeKeywordIndex"] = {}
_COLLECTION_FINGERPRINT: Optional[int] = None


@dataclass
class _ScopeKeywordIndex:
    docs: List[Document]
    postings: Dict[str, List[Tuple[int, int]]]
    doc_lengths: List[int]
    doc_freq: Dict[str, int]
    avg_doc_len: float

    def search(self, query: str, top_k: int = 3) -> List[Document]:
        tokens = _tokenize_text(query)
        if not tokens:
            return []

        k1 = 1.5
        b = 0.75
        n_docs = len(self.docs)
        if n_docs == 0:
            return []

        scores = defaultdict(float)
        unique_tokens = list(dict.fromkeys(tokens))
        for token in unique_tokens:
            postings = self.postings.get(token)
            if not postings:
                continue
            df = self.doc_freq.get(token, 0)
            if df <= 0:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for doc_id, tf in postings:
                doc_len = self.doc_lengths[doc_id]
                denom = tf + k1 * (1.0 - b + b * doc_len / max(1.0, self.avg_doc_len))
                score = idf * tf * (k1 + 1.0) / max(1e-6, denom)
                scores[doc_id] += score

        ranked_doc_ids = sorted(scores.items(), key=lambda item: item[1], reverse=True)[: max(1, top_k)]
        results: List[Document] = []
        for doc_id, score in ranked_doc_ids:
            source_doc = self.docs[doc_id]
            metadata = dict(source_doc.metadata or {})
            metadata["keyword_score"] = round(float(score), 6)
            results.append(Document(page_content=source_doc.page_content, metadata=metadata))
        return results


def _tokenize_text(text: str) -> List[str]:
    lowered = (text or "").lower()
    if not lowered:
        return []
    terms = [token.strip() for token in _TOKEN_PATTERN.findall(lowered) if token.strip()]
    # Add normalized multi-char medical terms to improve Chinese phrase matching.
    terms.extend(extract_query_terms(lowered))
    unique_terms = list(dict.fromkeys(t for t in terms if len(t) >= 2))
    return unique_terms[:48]


def _build_where_filter(scope: str, domain: str) -> dict:
    if domain == "medical":
        return {"department": scope}
    return {"domain": domain}


def _load_scope_docs(scope: str, domain: str) -> List[Document]:
    vectorstore = get_or_create_vectorstore()
    if not vectorstore:
        return []

    collection = vectorstore._collection
    where_filter = _build_where_filter(scope, domain)

    docs: List[Document] = []
    offset = 0
    batch_size = 1000
    while True:
        try:
            payload = collection.get(
                where=where_filter,
                limit=batch_size,
                offset=offset,
                include=["documents", "metadatas"],
            )
        except Exception as exc:
            logger.warning("Keyword retriever get() failed for scope=%s: %s", scope, exc)
            break

        batch_docs = payload.get("documents") or []
        batch_metadatas = payload.get("metadatas") or []
        if not batch_docs:
            break

        for idx, page_content in enumerate(batch_docs):
            if not isinstance(page_content, str) or len(page_content.strip()) < 20:
                continue
            metadata = {}
            if idx < len(batch_metadatas) and isinstance(batch_metadatas[idx], dict):
                metadata = dict(batch_metadatas[idx] or {})
            docs.append(Document(page_content=page_content, metadata=metadata))
        offset += len(batch_docs)
    return docs


def _build_scope_index(scope: str, domain: str) -> Optional[_ScopeKeywordIndex]:
    docs = _load_scope_docs(scope, domain)
    if not docs:
        return None

    postings: Dict[str, List[Tuple[int, int]]] = defaultdict(list)
    doc_freq: Dict[str, int] = defaultdict(int)
    doc_lengths: List[int] = []
    indexed_docs: List[Document] = []

    for raw_doc in docs:
        tokens = _tokenize_text(raw_doc.page_content)
        if not tokens:
            continue
        tf = Counter(tokens)
        doc_id = len(indexed_docs)
        indexed_docs.append(raw_doc)
        doc_lengths.append(sum(tf.values()))
        for token, count in tf.items():
            postings[token].append((doc_id, int(count)))
            doc_freq[token] += 1

    if not indexed_docs:
        return None

    avg_doc_len = float(sum(doc_lengths) / max(1, len(doc_lengths)))
    return _ScopeKeywordIndex(
        docs=indexed_docs,
        postings=dict(postings),
        doc_lengths=doc_lengths,
        doc_freq=dict(doc_freq),
        avg_doc_len=avg_doc_len,
    )


def _refresh_cache_if_needed() -> None:
    global _COLLECTION_FINGERPRINT
    vectorstore = get_or_create_vectorstore()
    if not vectorstore:
        return
    try:
        current_count = int(vectorstore._collection.count())
    except Exception:
        return
    if _COLLECTION_FINGERPRINT == current_count:
        return
    _INDEX_CACHE.clear()
    _COLLECTION_FINGERPRINT = current_count
    logger.info("Keyword retriever cache reset (collection_count=%d)", current_count)


def keyword_search(
    query: str,
    *,
    scope: str,
    domain: str,
    top_k: int = 3,
) -> List[Document]:
    """Run keyword retrieval for one scope using cached BM25-style index."""
    if not query.strip():
        return []
    with _INDEX_LOCK:
        _refresh_cache_if_needed()
        cache_key = f"{domain}::{scope}"
        index = _INDEX_CACHE.get(cache_key)
        if index is None:
            index = _build_scope_index(scope, domain)
            if index is None:
                return []
            _INDEX_CACHE[cache_key] = index
    return index.search(query, top_k=max(1, int(top_k)))

