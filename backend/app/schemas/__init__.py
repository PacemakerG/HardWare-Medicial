"""
MediGenius — schemas/__init__.py
Exports all Pydantic schemas.
"""

from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.auth import AuthStatusResponse, LoginRequest
from app.schemas.ecg import (
    ECGMonitorStartRequest,
    ECGMonitorStartResponse,
    ECGMonitorStatusResponse,
    ECGPatientInfo,
    ECGReportRequest,
    ECGReportResponse,
)
from app.schemas.session import MessageResponse, SessionResponse

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "LoginRequest",
    "AuthStatusResponse",
    "SessionResponse",
    "MessageResponse",
    "ECGPatientInfo",
    "ECGReportRequest",
    "ECGReportResponse",
    "ECGMonitorStartRequest",
    "ECGMonitorStartResponse",
    "ECGMonitorStatusResponse",
]
