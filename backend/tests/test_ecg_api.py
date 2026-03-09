import asyncio
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.api.v1.endpoints.ecg import (
    download_ecg_report_pdf_endpoint,
    generate_ecg_report_endpoint,
    get_ecg_monitor_status_endpoint,
    get_ecg_report_endpoint,
    start_ecg_monitor_endpoint,
)
from app.schemas.ecg import (
    ECGMonitorStartRequest,
    ECGMonitorStartResponse,
    ECGMonitorStatusResponse,
    ECGPatientInfo,
    ECGReportRequest,
    ECGReportResponse,
)


def _mock_ctx():
    return MagicMock(session_id="sess-1", tenant_id="tenant-a", user_id="user-a")


def test_ecg_report_endpoint():
    mock_response = ECGReportResponse(
        report_id="r-100",
        created_at="2026-03-06T00:00:00",
        report="**心电图诊断报告**\n\n**临床信息**\n...\n\n**建议**\n...",
        risk_level="low",
        key_findings=["算法预判: 正常心电图"],
        recommendations=["建议定期复查。"],
        disclaimer="本报告仅供临床辅助参考。",
        success=True,
    )

    payload = ECGReportRequest(
        patient_info=ECGPatientInfo(
            patient_id="17448",
            age=19,
            gender="male",
            height_cm=175,
            weight_kg=67,
            checkup_time="2026-01-12 17:48:07",
        ),
        diagnosis_codes=["NORM", "SR"],
        diagnosis_cn=["正常心电图", "窦性心律"],
        signal_quality="质量良好",
        features={"heart_rate": 66, "axis_degree": 29},
    )

    with patch(
        "app.api.v1.endpoints.ecg.ecg_report_service.generate_report",
        return_value=mock_response,
    ), patch("app.api.v1.endpoints.ecg._get_request_context", return_value=_mock_ctx()):
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.session = {}
        result = asyncio.run(generate_ecg_report_endpoint(payload, mock_req))

    assert result.success is True
    assert result.risk_level == "low"
    assert result.report_id == "r-100"


def test_get_ecg_report_endpoint():
    mock_response = ECGReportResponse(
        report_id="r-101",
        created_at="2026-03-06T00:00:01",
        report="**心电图诊断报告**\n...",
        risk_level="medium",
        key_findings=["心率偏快"],
        recommendations=["建议复查"],
        disclaimer="本报告仅供临床辅助参考。",
        success=True,
    )
    with patch(
        "app.api.v1.endpoints.ecg.ecg_report_service.get_report_by_id",
        return_value=mock_response,
    ), patch("app.api.v1.endpoints.ecg._get_request_context", return_value=_mock_ctx()):
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.session = {}
        result = asyncio.run(get_ecg_report_endpoint("r-101", mock_req))
    assert result.report_id == "r-101"
    assert result.risk_level == "medium"


def test_start_ecg_monitor_endpoint():
    payload = ECGMonitorStartRequest(
        patient_name="张三",
        age=30,
        gender="male",
        height_cm=175,
        weight_kg=70,
    )
    mock_resp = ECGMonitorStartResponse(
        task_id="task-1",
        status="queued",
        message="已开始监听",
        success=True,
    )
    with patch(
        "app.api.v1.endpoints.ecg.ecg_monitor_service.start_monitor",
        return_value=mock_resp,
    ), patch("app.api.v1.endpoints.ecg._get_request_context", return_value=_mock_ctx()):
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.session = {}
        result = asyncio.run(start_ecg_monitor_endpoint(payload, mock_req))

    assert result.task_id == "task-1"
    assert result.success is True


def test_get_ecg_monitor_status_endpoint():
    mock_status = ECGMonitorStatusResponse(
        task_id="task-1",
        status="completed",
        message="done",
        started_at="2026-03-08T00:00:00",
        updated_at="2026-03-08T00:00:30",
        report=ECGReportResponse(
            report_id="r1",
            created_at="2026-03-08T00:00:30",
            report="报告",
            risk_level="low",
            key_findings=["心率正常"],
            recommendations=["复查"],
            disclaimer="仅供参考",
            success=True,
        ),
        source_row={"username": "u1"},
        success=True,
    )
    with patch(
        "app.api.v1.endpoints.ecg.ecg_monitor_service.get_status",
        return_value=mock_status,
    ), patch("app.api.v1.endpoints.ecg._get_request_context", return_value=_mock_ctx()):
        mock_req = MagicMock()
        mock_req.headers = {}
        mock_req.session = {}
        result = asyncio.run(get_ecg_monitor_status_endpoint("task-1", mock_req))
    assert result.task_id == "task-1"
    assert result.status == "completed"


def test_download_ecg_report_pdf_endpoint():
    mock_response = ECGReportResponse(
        report_id="r-200",
        created_at="2026-03-06T00:00:03",
        report="报告正文",
        risk_level="low",
        key_findings=["正常"],
        recommendations=["随访"],
        disclaimer="本报告仅供临床辅助参考。",
        pdf_url="/api/v1/ecg/report/r-200/pdf",
        success=True,
    )
    with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp_pdf:
        with patch(
            "app.api.v1.endpoints.ecg.ecg_report_service.get_report_by_id",
            return_value=mock_response,
        ), patch(
            "app.api.v1.endpoints.ecg.get_report_pdf_path",
            return_value=Path(tmp_pdf.name),
        ), patch(
            "app.api.v1.endpoints.ecg._get_request_context",
            return_value=_mock_ctx(),
        ):
            mock_req = MagicMock()
            mock_req.headers = {}
            mock_req.session = {}
            result = asyncio.run(download_ecg_report_pdf_endpoint("r-200", mock_req))

    assert result.media_type == "application/pdf"
