"""
MediGenius — api/v1/endpoints/chat.py
Chat-related endpoints: /chat, /clear, /new-chat.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.api.v1.request_context import RequestContext, get_request_context
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service

router = APIRouter(tags=["Chat"])


def _get_session_id(request: Request) -> str:
    """Backward-compatible session accessor used by tests."""
    return get_request_context(request).session_id


def _get_request_context(request: Request) -> RequestContext:
    return get_request_context(request)


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, req: Request):
    """Process a user message through the agentic pipeline."""
    if not chat_service.workflow_app:
        raise HTTPException(status_code=503, detail="System not initialized")
    ctx = _get_request_context(req)
    return await chat_service.process_message(
        ctx.session_id,
        request.message,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )


@router.post("/clear")
async def clear_endpoint(req: Request):
    """Clear the in-memory conversation state for the current session."""
    ctx = _get_request_context(req)
    chat_service.clear_conversation(
        ctx.session_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    return {"message": "Conversation cleared", "success": True}


@router.post("/new-chat")
async def new_chat_endpoint(req: Request):
    """Create a new chat session with a fresh session ID."""
    _ = _get_request_context(req)
    new_id = str(uuid.uuid4())
    req.session["session_id"] = new_id
    return {"message": "New chat created", "session_id": new_id, "success": True}
