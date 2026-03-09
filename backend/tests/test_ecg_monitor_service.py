from pathlib import Path
import importlib

from app.schemas.ecg import ECGMonitorStartRequest, ECGReportResponse
from app.services.ecg_monitor_service import ECGMonitorService
monitor_module = importlib.import_module("app.services.ecg_monitor_service")


class _FakeLoginConfig:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


class _FakeClient:
    def __init__(self, _cfg):
        self._rows = [
            {"username": "doctor_a", "createTime": "2026-03-08 10:00:00", "userId": 1},
        ]
        self._idx = 0

    def login(self):
        return None

    def get_latest_row(self):
        row = self._rows[min(self._idx, len(self._rows) - 1)]
        self._idx += 1
        return row

    def download_latest_xls(self, _row, output_dir: Path):
        return output_dir / "latest.xls"


class _FakeHardwareModule:
    LoginConfig = _FakeLoginConfig
    ECGWebClient = _FakeClient

    @staticmethod
    def parse_xls_file(_xls_path):
        return {"mocked": True}

    @staticmethod
    def build_record(_latest_row, _parsed_xls, _xls_path, sample_rate_hz=500):
        return {
            "skill_request": {
                "patient_info": {
                    "patient_id": "p1",
                    "age": 29,
                    "gender": "male",
                    "height_cm": 170,
                    "weight_kg": 65,
                    "checkup_time": "2026-03-08 10:00:00",
                },
                "diagnosis_codes": ["SR"],
                "diagnosis_cn": ["窦性心律"],
                "signal_quality": "质量良好",
                "features": {"heart_rate": 72},
                "notes": None,
            }
        }


def test_monitor_fetch_latest_and_llm_io_contract(monkeypatch):
    service = ECGMonitorService()
    intake = ECGMonitorStartRequest(patient_name="张三", age=29, gender="male")

    monkeypatch.setattr(
        monitor_module,
        "_load_hardware_fetch_module",
        lambda: _FakeHardwareModule,
    )
    monkeypatch.setattr(
        monitor_module.ecg_report_service,
        "generate_report",
        lambda *_args, **_kwargs: ECGReportResponse(
            report_id="r-1",
            created_at="2026-03-08T10:00:10",
            report="报告正文",
            risk_level="low",
            key_findings=["窦性心律"],
            recommendations=["随访"],
            disclaimer="仅供参考",
            success=True,
        ),
    )

    task_id = "task-timeout-fallback"
    service._worker(task_id, "session-1", "tenant-a", "user-a", intake.model_dump())
    status = service.get_status(
        task_id,
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="session-1",
    )

    assert status is not None
    assert status.success is True
    assert status.status == "completed"
    assert "网站最新一条" in status.message
    assert status.llm_input is not None
    assert status.llm_output is not None
    assert "report" not in status.llm_input
    assert status.llm_output["report"] == "报告正文"
    assert set(status.llm_output.keys()) == set(status.llm_input.keys()) | {"report"}


def test_monitor_status_isolation_by_identity():
    service = ECGMonitorService()
    service._save_task(
        "task-isolated",
        status="completed",
        message="ok",
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="sess-a",
        success=True,
    )

    assert service.get_status(
        "task-isolated",
        tenant_id="tenant-a",
        user_id="user-a",
        session_id="sess-a",
    ) is not None
    assert service.get_status(
        "task-isolated",
        tenant_id="tenant-b",
        user_id="user-a",
        session_id="sess-a",
    ) is None
