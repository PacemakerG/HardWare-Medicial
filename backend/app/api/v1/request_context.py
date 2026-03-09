"""
MediGenius — api/v1/request_context.py
Resolve tenant/user/session identity from request headers + cookie session.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from fastapi import Request

DEFAULT_TENANT_ID = "default"
DEFAULT_USER_ID = "anonymous"


def _sanitize_id(value: str | None, default: str, max_len: int = 128) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        return default
    text = (value or "").strip()
    if not text:
        return default
    safe = re.sub(r"[^a-zA-Z0-9_.:@/-]", "_", text)
    safe = safe.strip("._-") or default
    return safe[:max_len]


def _get_query_param(request: Request, key: str) -> str | None:
    params = getattr(request, "query_params", None)
    if params is None:
        return None
    try:
        value = params.get(key)
    except Exception:
        return None
    return value if isinstance(value, str) else None


@dataclass(frozen=True)
class RequestContext:
    tenant_id: str
    user_id: str
    session_id: str


def get_request_context(request: Request) -> RequestContext:
    tenant_source = (
        request.headers.get("X-Tenant-ID")
        or _get_query_param(request, "tenant_id")
        or request.session.get("tenant_id")
    )
    user_source = (
        request.headers.get("X-User-ID")
        or _get_query_param(request, "user_id")
        or request.session.get("user_id")
    )
    session_source = (
        request.headers.get("X-Session-ID")
        or _get_query_param(request, "session_id")
        or request.session.get("session_id")
    )

    tenant_id = _sanitize_id(tenant_source, DEFAULT_TENANT_ID)
    user_id = _sanitize_id(user_source, DEFAULT_USER_ID)

    if not session_source:
        session_source = str(uuid.uuid4())
    session_id = _sanitize_id(str(session_source), str(uuid.uuid4()), max_len=255)

    # Keep cookie session aligned for browser-only clients without custom headers.
    request.session["tenant_id"] = tenant_id
    request.session["user_id"] = user_id
    request.session["session_id"] = session_id

    return RequestContext(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
    )
