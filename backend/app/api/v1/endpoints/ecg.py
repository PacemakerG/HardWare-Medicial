"""
MediGenius — api/v1/endpoints/ecg.py
ECG report generation endpoint.
"""

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.schemas.ecg import ECGReportRequest, ECGReportResponse
from app.services.ecg_report_service import ecg_report_service

router = APIRouter(prefix="/ecg", tags=["ECG"])


def _get_session_id(request: Request) -> str:
    session_id = request.headers.get("X-Session-ID")
    if session_id:
        return session_id
    if "session_id" not in request.session:
        request.session["session_id"] = str(uuid.uuid4())
    return request.session["session_id"]


@router.post("/report", response_model=ECGReportResponse)
async def generate_ecg_report_endpoint(request: ECGReportRequest, req: Request):
    """Generate a structured ECG medical report from parameters."""
    return ecg_report_service.generate_report(request, session_id=_get_session_id(req))


@router.get("/report/{report_id}", response_model=ECGReportResponse)
async def get_ecg_report_endpoint(report_id: str):
    """Get a previously generated ECG report by report_id."""
    report = ecg_report_service.get_report_by_id(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="ECG report not found")
    return report
