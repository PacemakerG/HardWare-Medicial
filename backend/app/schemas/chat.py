"""
MediGenius — schemas/chat.py
Pydantic schemas for chat request/response and welcome-message payloads.
"""

from typing import List

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str
    selected_department: str | None = None


class ChatResponse(BaseModel):
    response: str
    source: str
    timestamp: str
    success: bool
    flow_trace: List[str]


class WelcomeRequest(BaseModel):
    latitude: float | None = None
    longitude: float | None = None
    timezone: str | None = None
    locale: str | None = None


class WelcomeResponse(BaseModel):
    response: str
    source: str
    timestamp: str
    success: bool
    session_id: str
    created: bool = True
    context_used: List[str] = Field(default_factory=list)
