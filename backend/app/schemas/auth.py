"""
MediGenius — schemas/auth.py
Pydantic schemas for lightweight web login.
"""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=128)


class AuthStatusResponse(BaseModel):
    logged_in: bool
    tenant_id: str
    user_id: str
    session_id: str
    success: bool = True
