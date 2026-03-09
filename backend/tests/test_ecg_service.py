from unittest.mock import MagicMock, patch

from app.schemas.ecg import ECGPatientInfo, ECGReportRequest
from app.services.ecg_report_service import ECGReportService


def _sample_request() -> ECGReportRequest:
    return ECGReportRequest(
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
        features={"heart_rate": 66, "axis_degree": 29, "axis_desc": "正常心电轴"},
    )


def test_generate_report_with_llm():
    service = ECGReportService()
    request = _sample_request()

    with patch("app.services.ecg_report_service.get_llm") as mock_get, \
            patch("app.services.ecg_report_service.db_service.save_ecg_report") as mock_save, \
            patch("app.services.ecg_report_service.generate_ecg_pdf", return_value="/tmp/r1.pdf"), \
            patch("app.services.ecg_report_service.os.path.exists", return_value=True), \
            patch("app.services.ecg_report_service.update_profile") as mock_update_profile:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "**心电图诊断报告**\n\n**临床信息**\n...\n\n**建议**\n..."
        mock_get.return_value = mock_llm
        mock_save.return_value = {"report_id": "r1", "created_at": "2026-03-06T00:00:00"}
        result = service.generate_report(request, session_id="sess-1")

    assert result.success is True
    assert "心电图诊断报告" in result.report
    assert result.risk_level in {"low", "medium", "high"}
    assert len(result.recommendations) >= 1
    assert result.report_id == "r1"
    assert result.pdf_url == "/api/v1/ecg/report/r1/pdf"
    mock_update_profile.assert_called_once()


def test_generate_report_fallback_without_llm():
    service = ECGReportService()
    request = _sample_request()

    with patch("app.services.ecg_report_service.get_llm", return_value=None), \
            patch("app.services.ecg_report_service.db_service.save_ecg_report") as mock_save, \
            patch("app.services.ecg_report_service.generate_ecg_pdf", return_value=None):
        mock_save.return_value = {"report_id": "r2", "created_at": "2026-03-06T00:00:01"}
        result = service.generate_report(request)

    assert result.success is True
    assert "临床信息" in result.report
    assert "建议" in result.report
    assert result.report_id == "r2"


def test_generate_report_high_risk_has_urgent_alert():
    service = ECGReportService()
    req = _sample_request()
    req.features["heart_rate"] = 150

    with patch("app.services.ecg_report_service.get_llm", return_value=None), \
            patch("app.services.ecg_report_service.db_service.save_ecg_report") as mock_save, \
            patch("app.services.ecg_report_service.generate_ecg_pdf", return_value=None):
        mock_save.return_value = {"report_id": "r3", "created_at": "2026-03-06T00:00:02"}
        result = service.generate_report(req)

    assert result.risk_level == "high"
    assert "急诊" in result.report or "紧急" in result.report
