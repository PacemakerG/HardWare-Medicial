"""
MediGenius — api/v1/endpoints/ecg.py
ECG report generation endpoint.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse

from app.api.v1.request_context import RequestContext, get_request_context
from app.schemas.ecg import (
    ECGMonitorStartRequest,
    ECGMonitorStartResponse,
    ECGMonitorStatusResponse,
    ECGReportRequest,
    ECGReportResponse,
)
from app.services.ecg_monitor_service import ecg_monitor_service
from app.services.ecg_pdf_service import get_report_pdf_path
from app.services.ecg_report_service import ecg_report_service

router = APIRouter(prefix="/ecg", tags=["ECG"])


def _get_session_id(request: Request) -> str:
    return get_request_context(request).session_id


def _get_request_context(request: Request) -> RequestContext:
    return get_request_context(request)


@router.post("/report", response_model=ECGReportResponse)
async def generate_ecg_report_endpoint(request: ECGReportRequest, req: Request):
    """Generate a structured ECG medical report from parameters."""
    ctx = _get_request_context(req)
    return ecg_report_service.generate_report(
        request,
        session_id=ctx.session_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )


@router.get("/report/{report_id}", response_model=ECGReportResponse)
async def get_ecg_report_endpoint(report_id: str, req: Request):
    """Get a previously generated ECG report by report_id."""
    ctx = _get_request_context(req)
    report = ecg_report_service.get_report_by_id(
        report_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    if not report:
        raise HTTPException(status_code=404, detail="ECG report not found")
    return report


@router.get("/report/{report_id}/pdf")
async def download_ecg_report_pdf_endpoint(report_id: str, req: Request):
    """Download ECG PDF report by report_id."""
    ctx = _get_request_context(req)
    report = ecg_report_service.get_report_by_id(
        report_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
    )
    if not report:
        raise HTTPException(status_code=404, detail="ECG report not found")

    pdf_path = get_report_pdf_path(report_id)
    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail="ECG report PDF not found")

    return FileResponse(
        str(pdf_path),
        media_type="application/pdf",
        filename=f"ecg_report_{report_id}.pdf",
    )


@router.post("/monitor/start", response_model=ECGMonitorStartResponse)
async def start_ecg_monitor_endpoint(request: ECGMonitorStartRequest, req: Request):
    """Start ECG monitor task and generate report from configured live/synthetic source."""
    ctx = _get_request_context(req)
    return ecg_monitor_service.start_monitor(
        session_id=ctx.session_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        intake=request,
    )


@router.get("/monitor/{task_id}", response_model=ECGMonitorStatusResponse)
async def get_ecg_monitor_status_endpoint(task_id: str, req: Request):
    """Fetch monitor task status and final ECG report if completed."""
    ctx = _get_request_context(req)
    status = ecg_monitor_service.get_status(
        task_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
    )
    if not status:
        raise HTTPException(status_code=404, detail="ECG monitor task not found")
    return status


@router.get("/monitor/{task_id}/events")
async def stream_ecg_monitor_status_events(task_id: str, req: Request):
    """
    SSE stream for ECG monitor task status updates.
    Client keeps a single connection open and receives push updates.
    """
    ctx = _get_request_context(req)
    first_status = ecg_monitor_service.get_status(
        task_id,
        tenant_id=ctx.tenant_id,
        user_id=ctx.user_id,
        session_id=ctx.session_id,
    )
    if not first_status:
        raise HTTPException(status_code=404, detail="ECG monitor task not found")

    async def _event_generator():
        status = first_status
        last_updated = status.updated_at
        yield f"data: {json.dumps(status.model_dump(), ensure_ascii=False)}\n\n"
        if status.status in {"completed", "failed"}:
            return

        while True:
            update = await asyncio.to_thread(
                ecg_monitor_service.wait_for_status_update,
                task_id,
                tenant_id=ctx.tenant_id,
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                last_updated_at=last_updated,
                timeout_sec=15.0,
            )
            if update is None:
                # SSE comment frame as keepalive
                yield ": keepalive\n\n"
                continue

            last_updated = update.updated_at
            yield f"data: {json.dumps(update.model_dump(), ensure_ascii=False)}\n\n"
            if update.status in {"completed", "failed"}:
                return

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
