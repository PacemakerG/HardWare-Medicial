"""
MediGenius — services/langsmith_service.py
LangSmith tracing helpers and compatibility bootstrap.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any, Callable

from app.core.config import (
    LANGSMITH_API_KEY,
    LANGSMITH_ENDPOINT,
    LANGSMITH_PROJECT,
    LANGSMITH_TAGS,
    LANGSMITH_TRACING,
    LANGSMITH_WORKSPACE_ID,
)
from app.core.logging_config import logger


def _identity_decorator(func: Callable) -> Callable:
    return func


def _normalized_tags(extra_tags: list[str] | None = None) -> list[str]:
    configured = [tag.strip() for tag in str(LANGSMITH_TAGS or "").split(",") if tag.strip()]
    extras = [tag.strip() for tag in (extra_tags or []) if str(tag).strip()]
    merged: list[str] = []
    seen = set()
    for tag in configured + extras:
        if tag in seen:
            continue
        seen.add(tag)
        merged.append(tag)
    return merged


def is_langsmith_enabled() -> bool:
    return bool(LANGSMITH_TRACING and LANGSMITH_API_KEY)


@lru_cache(maxsize=1)
def configure_langsmith() -> bool:
    """Configure environment compatibility flags for LangSmith/LangChain tracing."""
    if not LANGSMITH_TRACING:
        logger.info("LangSmith tracing disabled")
        return False

    if not LANGSMITH_API_KEY:
        logger.warning("LangSmith tracing enabled but LANGSMITH_API_KEY is missing")
        return False

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGCHAIN_API_KEY"] = LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
    os.environ["LANGCHAIN_PROJECT"] = LANGSMITH_PROJECT

    if LANGSMITH_ENDPOINT:
        os.environ["LANGSMITH_ENDPOINT"] = LANGSMITH_ENDPOINT
        os.environ["LANGCHAIN_ENDPOINT"] = LANGSMITH_ENDPOINT
    if LANGSMITH_WORKSPACE_ID:
        os.environ["LANGSMITH_WORKSPACE_ID"] = LANGSMITH_WORKSPACE_ID

    logger.info("LangSmith tracing enabled for project=%s", LANGSMITH_PROJECT)
    return True


def langsmith_traceable(
    name: str,
    *,
    run_type: str = "chain",
) -> Callable[[Callable], Callable]:
    """Return LangSmith traceable decorator when available, otherwise no-op."""
    try:
        from langsmith import traceable

        return traceable(name=name, run_type=run_type)
    except Exception as exc:
        logger.debug("LangSmith traceable unavailable for %s: %s", name, exc)
        return _identity_decorator


def build_langsmith_runnable_config(
    *,
    operation: str,
    session_id: str,
    tenant_id: str,
    user_id: str,
    selected_department: str | None = None,
    extra_tags: list[str] | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build RunnableConfig metadata so LangGraph/LangChain traces are easier to inspect."""
    metadata = {
        "operation": operation,
        "session_id": session_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
    }
    if selected_department:
        metadata["selected_department"] = selected_department
    if extra_metadata:
        metadata.update(extra_metadata)

    return {
        "run_name": operation,
        "tags": _normalized_tags(extra_tags),
        "metadata": metadata,
        "configurable": {
            "thread_id": session_id or "default-thread",
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
    }
