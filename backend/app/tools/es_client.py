"""
MediGenius — tools/es_client.py
Minimal Elasticsearch/OpenSearch REST client for keyword indexing and search.
"""

from __future__ import annotations

import json
from typing import Any, Iterable

import httpx
from langchain_core.documents import Document

from app.core.config import (
    ES_ENABLED,
    ES_HOST,
    ES_INDEX_NAME,
    ES_PASSWORD,
    ES_TIMEOUT_SECONDS,
    ES_USERNAME,
    ES_VERIFY_CERTS,
)
from app.core.logging_config import logger


def _base_headers() -> dict[str, str]:
    return {"Content-Type": "application/json"}


def _bulk_headers() -> dict[str, str]:
    return {"Content-Type": "application/x-ndjson"}


def _auth() -> tuple[str, str] | None:
    if ES_USERNAME:
        return (ES_USERNAME, ES_PASSWORD or "")
    return None


def _client() -> httpx.Client:
    return httpx.Client(
        base_url=ES_HOST.rstrip("/"),
        headers=_base_headers(),
        timeout=ES_TIMEOUT_SECONDS,
        verify=ES_VERIFY_CERTS,
        auth=_auth(),
    )


def es_enabled() -> bool:
    return bool(ES_ENABLED and ES_HOST and ES_INDEX_NAME)


def ensure_es_index() -> bool:
    """Create index on demand with a lightweight BM25-friendly mapping."""
    if not es_enabled():
        return False

    mapping = {
        "settings": {
            "index": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
            }
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "keyword"},
                "content": {"type": "text"},
                "tenant_id": {"type": "keyword"},
                "domain": {"type": "keyword"},
                "department": {"type": "keyword"},
                "source_book": {"type": "keyword"},
                "source_path": {"type": "keyword"},
                "source_type": {"type": "keyword"},
                "page": {"type": "integer"},
                "section": {"type": "keyword"},
                "section_index": {"type": "integer"},
                "chunk_strategy": {"type": "keyword"},
                "chunk_level": {"type": "keyword"},
                "parent_chunk_id": {"type": "keyword"},
                "parent_index": {"type": "integer"},
                "child_index": {"type": "integer"},
                "parent_excerpt": {"type": "text"},
            }
        },
    }

    try:
        with _client() as client:
            exists = client.head(f"/{ES_INDEX_NAME}")
            if exists.status_code == 200:
                return True
            response = client.put(f"/{ES_INDEX_NAME}", json=mapping)
            if response.is_success:
                logger.info("Elasticsearch index ready: %s", ES_INDEX_NAME)
                return True
            logger.warning(
                "Failed to create Elasticsearch index=%s status=%s body=%s",
                ES_INDEX_NAME,
                response.status_code,
                response.text[:400],
            )
    except Exception as exc:
        logger.warning("Elasticsearch index initialization failed: %s", exc)
    return False


def es_document_count() -> int:
    if not es_enabled():
        return 0
    try:
        with _client() as client:
            response = client.get(f"/{ES_INDEX_NAME}/_count")
            if response.is_success:
                payload = response.json()
                return int(payload.get("count") or 0)
    except Exception:
        return 0
    return 0


def _document_to_es_payload(doc: Document) -> dict[str, Any]:
    metadata = dict(doc.metadata or {})
    return {
        "chunk_id": metadata.get("chunk_id"),
        "content": doc.page_content,
        "tenant_id": metadata.get("tenant_id", "default"),
        "domain": metadata.get("domain", ""),
        "department": metadata.get("department", ""),
        "source_book": metadata.get("source_book", ""),
        "source_path": metadata.get("source_path") or metadata.get("source") or "",
        "source_type": metadata.get("source_type", ""),
        "page": metadata.get("page"),
        "section": metadata.get("section"),
        "section_index": metadata.get("section_index"),
        "chunk_strategy": metadata.get("chunk_strategy", ""),
        "chunk_level": metadata.get("chunk_level", ""),
        "parent_chunk_id": metadata.get("parent_chunk_id", ""),
        "parent_index": metadata.get("parent_index"),
        "child_index": metadata.get("child_index"),
        "parent_excerpt": metadata.get("parent_excerpt", ""),
    }


def bulk_index_documents(documents: Iterable[Document]) -> bool:
    """Upsert chunk documents into Elasticsearch using chunk_id as stable _id."""
    if not ensure_es_index():
        return False

    lines: list[str] = []
    indexed = 0
    for document in documents:
        if not isinstance(document, Document):
            continue
        payload = _document_to_es_payload(document)
        chunk_id = payload.get("chunk_id")
        if not chunk_id:
            continue
        lines.append(json.dumps({"index": {"_index": ES_INDEX_NAME, "_id": chunk_id}}, ensure_ascii=False))
        lines.append(json.dumps(payload, ensure_ascii=False))
        indexed += 1

    if not lines:
        return False

    body = "\n".join(lines) + "\n"
    try:
        with _client() as client:
            response = client.post("/_bulk", content=body, headers=_bulk_headers())
            if response.is_success:
                logger.info("Indexed %d chunk(s) into Elasticsearch", indexed)
                return True
            logger.warning(
                "Elasticsearch bulk index failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
    except Exception as exc:
        logger.warning("Elasticsearch bulk index failed: %s", exc)
    return False
