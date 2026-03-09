"""
MediGenius — api/v1/endpoints/auth.py
Lightweight auth endpoints for browser login state.
"""

from fastapi import APIRouter, Request

from app.api.v1.request_context import (
    DEFAULT_TENANT_ID,
    DEFAULT_USER_ID,
    get_request_context,
)
from app.schemas.auth import AuthStatusResponse, LoginRequest

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.get("/me", response_model=AuthStatusResponse)
async def auth_me_endpoint(req: Request):
    ctx = get_request_context(req)
    return AuthStatusResponse(
        logged_in=ctx.user_id != DEFAULT_USER_ID,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        success=True,
    )


@router.post("/login", response_model=AuthStatusResponse)
async def auth_login_endpoint(payload: LoginRequest, req: Request):
    req.session["tenant_id"] = (payload.tenant_id or DEFAULT_TENANT_ID).strip() or DEFAULT_TENANT_ID
    req.session["user_id"] = payload.user_id.strip()
    ctx = get_request_context(req)
    return AuthStatusResponse(
        logged_in=True,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        success=True,
    )


@router.post("/logout", response_model=AuthStatusResponse)
async def auth_logout_endpoint(req: Request):
    req.session["user_id"] = DEFAULT_USER_ID
    ctx = get_request_context(req)
    return AuthStatusResponse(
        logged_in=False,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
        success=True,
    )
