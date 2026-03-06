import asyncio
from unittest.mock import MagicMock, patch

from app.api.v1.endpoints.ecg import generate_ecg_report_endpoint, get_ecg_report_endpoint
from app.schemas.ecg import ECGPatientInfo, ECGReportRequest, ECGReportResponse


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
    ), patch("app.api.v1.endpoints.ecg._get_session_id", return_value="sess-1"):
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
    ):
        result = asyncio.run(get_ecg_report_endpoint("r-101"))
    assert result.report_id == "r-101"
    assert result.risk_level == "medium"
