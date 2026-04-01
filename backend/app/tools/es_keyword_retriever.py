"""
MediGenius — tools/es_keyword_retriever.py
Elasticsearch-backed keyword retrieval for hybrid medical search.
"""

from __future__ import annotations

from typing import List

import httpx
from langchain_core.documents import Document

from app.core.config import (
    ES_HOST,
    ES_INDEX_NAME,
    ES_PASSWORD,
    ES_TIMEOUT_SECONDS,
    ES_USERNAME,
    ES_VERIFY_CERTS,
)
from app.core.logging_config import logger
from app.tools.es_client import ensure_es_index, es_enabled


def _auth() -> tuple[str, str] | None:
    if ES_USERNAME:
        return (ES_USERNAME, ES_PASSWORD or "")
    return None


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=ES_HOST.rstrip("/"),
        timeout=ES_TIMEOUT_SECONDS,
        verify=ES_VERIFY_CERTS,
        auth=_auth(),
    )


def keyword_search_es(
    query: str,
    *,
    scope: str,
    domain: str,
    top_k: int = 3,
) -> List[Document]:
    """Run BM25 keyword retrieval in Elasticsearch with strict scope/domain filtering."""
    if not query.strip():
        return []
    if not ensure_es_index():
        return []

    filters = [{"term": {"domain": domain}}]
    if domain == "medical":
        filters.append({"term": {"department": scope}})

    payload = {
        "size": max(1, int(top_k)),
        "query": {
            "bool": {
                "must": [
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["content^3", "source_book^1.2", "parent_excerpt"],
                            "type": "best_fields",
                        }
                    }
                ],
                "filter": filters,
            }
        },
    }

    try:
        with _client() as client:
            response = client.post(f"/{ES_INDEX_NAME}/_search", json=payload)
            if not response.is_success:
                logger.warning(
                    "Elasticsearch keyword search failed status=%s body=%s",
                    response.status_code,
                    response.text[:400],
                )
                return []
            hits = (response.json().get("hits") or {}).get("hits") or []
    except Exception as exc:
        logger.warning("Elasticsearch keyword search failed for scope=%s: %s", scope, exc)
        return []

    documents: List[Document] = []
    for item in hits:
        source = item.get("_source") or {}
        content = str(source.get("content") or "").strip()
        if len(content) < 20:
            continue
        metadata = {
            "chunk_id": source.get("chunk_id"),
            "tenant_id": source.get("tenant_id"),
            "domain": source.get("domain"),
            "department": source.get("department"),
            "source_book": source.get("source_book"),
            "source_path": source.get("source_path"),
            "source_type": source.get("source_type"),
            "page": source.get("page"),
            "section": source.get("section"),
            "section_index": source.get("section_index"),
            "chunk_strategy": source.get("chunk_strategy"),
            "chunk_level": source.get("chunk_level"),
            "parent_chunk_id": source.get("parent_chunk_id"),
            "parent_index": source.get("parent_index"),
            "child_index": source.get("child_index"),
            "parent_excerpt": source.get("parent_excerpt"),
            "keyword_score": round(float(item.get("_score") or 0.0), 6),
        }
        documents.append(Document(page_content=content, metadata=metadata))
    return documents


def keyword_backend_available() -> bool:
    return es_enabled()
