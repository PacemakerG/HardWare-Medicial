"""
MediGenius — api/v1/endpoints/session.py
Session management endpoints: /history, /sessions, /session/{id}.
"""

import uuid

from fastapi import APIRouter, Request

from app.api.v1.request_context import RequestContext, get_request_context
from app.services.database_service import db_service

router = APIRouter(tags=["Session"])


def _get_session_id(request: Request) -> str:
    """Backward-compatible session accessor used by tests."""
    return get_request_context(request).session_id


def _get_request_context(request: Request) -> RequestContext:
    return get_request_context(request)


@router.get("/history")
async def get_history_endpoint(req: Request):
    """Return the chat history for the current session."""
    ctx = _get_request_context(req)
    return {
        "messages": db_service.get_chat_history(
            ctx.session_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
        ),
        "success": True,
    }


@router.get("/sessions")
async def get_sessions_endpoint(req: Request):
    """Return a list of all chat sessions with previews."""
    ctx = _get_request_context(req)
    return {
        "sessions": db_service.get_all_sessions(
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
        ),
        "success": True,
    }


@router.get("/session/{session_id}")
async def load_session_endpoint(session_id: str, req: Request):
    """Load a specific session by ID and set it as the active session."""
    ctx = _get_request_context(req)
    req.session["session_id"] = session_id
    return {
        "messages": db_service.get_chat_history(
            session_id,
            tenant_id=ctx.tenant_id,
            user_id=ctx.user_id,
        ),
        "session_id": session_id,
        "success": True,
    }


@router.delete("/session/{session_id}")
async def delete_session_endpoint(session_id: str, req: Request):
    """Delete a session and reset the active session if it matches."""
    ctx = _get_request_context(req)
    db_service.delete_session(
        session_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    if req.session.get("session_id") == session_id:
        req.session["session_id"] = str(uuid.uuid4())
    return {"message": "Session deleted", "success": True}
