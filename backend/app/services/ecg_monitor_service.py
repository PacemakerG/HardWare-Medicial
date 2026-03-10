"""
MediGenius — services/ecg_monitor_service.py
Background ECG monitor workflow:
1) Receive basic patient info from frontend.
2) Choose data source: live cloud fetch or synthetic normal waveform.
3) Build ECG skill payload (from fetched XLS or synthetic waveform).
4) Generate ECG report and expose task status for frontend polling.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.core.config import (
    ECG_MONITOR_DATA_MODE,
    ECG_MONITOR_TARGET_CREATE_TIME,
    ECG_SITE_PASS,
    ECG_SITE_URL,
    ECG_SITE_USER,
)
from app.core.logging_config import logger
from app.schemas.ecg import (
    ECGMonitorStartRequest,
    ECGMonitorStartResponse,
    ECGMonitorStatusResponse,
    ECGReportRequest,
)
from app.services.ecg_report_service import ecg_report_service
from app.services.profile_service import update_profile

_HARDWARE_MODULE = None
_HARDWARE_MODULE_LOCK = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_site_base_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        default_parsed = urlparse(ECG_SITE_URL)
        if default_parsed.scheme and default_parsed.netloc:
            return f"{default_parsed.scheme}://{default_parsed.netloc}"
        return "http://127.0.0.1:8080"
    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return raw


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(value))
    except Exception:
        return None


def _normalize_profile_gender(gender: str) -> str:
    g = (gender or "").strip().lower()
    if g in {"male", "m", "男", "男性"}:
        return "male"
    if g in {"female", "f", "女", "女性"}:
        return "female"
    return "other"


def _project_root_dir() -> Path:
    # backend/app/services -> backend -> project root
    return Path(__file__).resolve().parents[3]


def _default_output_dir() -> Path:
    return _project_root_dir() / "hardware" / "ECGdata"


def _load_hardware_fetch_module():
    global _HARDWARE_MODULE
    if _HARDWARE_MODULE is not None:
        return _HARDWARE_MODULE

    with _HARDWARE_MODULE_LOCK:
        if _HARDWARE_MODULE is not None:
            return _HARDWARE_MODULE

        module_path = _project_root_dir() / "hardware" / "fetch_latest_ecg_and_convert.py"
        if not module_path.exists():
            raise RuntimeError(f"hardware fetch script not found: {module_path}")

        spec = importlib.util.spec_from_file_location("ecg_hardware_fetch", str(module_path))
        if spec is None or spec.loader is None:
            raise RuntimeError("failed to create hardware module spec")

        module = importlib.util.module_from_spec(spec)
        # Ensure dataclass/type evaluation can resolve module namespace during execution.
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(spec.name, None)
            raise
        _HARDWARE_MODULE = module
        return module


def _build_llm_io_payload(skill_payload: Dict[str, Any], report_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Keep LLM input/output JSON contract aligned.
    Output differs from input only by an optional `report` field.
    """
    payload = {
        "patient_info": dict(skill_payload.get("patient_info") or {}),
        "diagnosis_codes": list(skill_payload.get("diagnosis_codes") or []),
        "diagnosis_cn": list(skill_payload.get("diagnosis_cn") or []),
        "signal_quality": skill_payload.get("signal_quality") or "未知",
        "features": dict(skill_payload.get("features") or {}),
        "notes": skill_payload.get("notes"),
    }
    if report_text is not None:
        payload["report"] = report_text
    return payload


def _normalize_monitor_mode(mode: Optional[str]) -> str:
    raw = (mode or "").strip().lower()
    if raw in {"synthetic_normal", "mock_normal", "fake_normal", "demo_normal"}:
        return "synthetic_normal"
    return "live"


def _resolve_monitor_mode(request_mode: Optional[str]) -> str:
    return _normalize_monitor_mode(request_mode or ECG_MONITOR_DATA_MODE)


def _synthetic_lead_ii_waveform(
    sample_rate_hz: int,
    *,
    duration_sec: float = 10.0,
    heart_rate: float = 72.0,
) -> list[float]:
    sample_rate = max(100, int(sample_rate_hz or 500))
    total_samples = max(sample_rate, int(duration_sec * sample_rate))
    beat_period_sec = 60.0 / max(35.0, float(heart_rate))
    signal: list[float] = []

    for idx in range(total_samples):
        t = idx / float(sample_rate)
        phase = (t % beat_period_sec) / beat_period_sec

        p = 0.12 * math.exp(-0.5 * ((phase - 0.18) / 0.030) ** 2)
        q = -0.14 * math.exp(-0.5 * ((phase - 0.36) / 0.012) ** 2)
        r = 1.05 * math.exp(-0.5 * ((phase - 0.40) / 0.012) ** 2)
        s = -0.28 * math.exp(-0.5 * ((phase - 0.44) / 0.016) ** 2)
        tw = 0.32 * math.exp(-0.5 * ((phase - 0.70) / 0.060) ** 2)
        baseline = 0.015 * math.sin(2.0 * math.pi * 0.33 * t)
        mains = 0.004 * math.sin(2.0 * math.pi * 50.0 * t)

        signal.append(round(p + q + r + s + tw + baseline + mains, 6))

    return signal


def _build_synthetic_normal_payload(
    intake: ECGMonitorStartRequest,
    *,
    target_create_time: Optional[str] = None,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    sample_rate_hz = int(intake.sample_rate_hz or 500)
    heart_rate = 72.0
    lead_ii = _synthetic_lead_ii_waveform(
        sample_rate_hz,
        duration_sec=10.0,
        heart_rate=heart_rate,
    )
    checkup_time = (target_create_time or "").strip() or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    rr_mean_ms = round(60000.0 / heart_rate, 2)

    skill_payload = {
        "patient_info": {
            "patient_id": intake.patient_id,
            "patient_name": intake.patient_name,
            "age": intake.age,
            "gender": intake.gender,
            "height_cm": _safe_float(intake.height_cm),
            "weight_kg": _safe_float(intake.weight_kg),
            "checkup_time": checkup_time,
        },
        "diagnosis_codes": ["NORM", "SR"],
        "diagnosis_cn": ["正常心电图", "窦性心律"],
        "signal_quality": "质量良好",
        "features": {
            "heart_rate": heart_rate,
            "axis_degree": 52,
            "axis_desc": "正常电轴",
            "rr_interval_ms_mean": rr_mean_ms,
            "rr_interval_ms_std": 18.4,
            "pr_interval_ms": 158,
            "qrs_duration_ms": 92,
            "qt_interval_ms": 382,
            "qtc_ms": 411,
            "st_deviation_mv": 0.01,
            "p_wave_duration_ms": 96,
            "t_wave_duration_ms": 164,
            "rhythm_type": "窦性心律",
            "arrhythmia_flags": [],
            "r_peak_count": int(round((len(lead_ii) / max(sample_rate_hz, 1)) * heart_rate / 60.0)),
            "sample_rate_hz": sample_rate_hz,
            "sample_count": len(lead_ii),
            "duration_sec": round(len(lead_ii) / float(max(sample_rate_hz, 1)), 3),
            "signal_quality_score": 0.97,
            "noise_ratio": 0.03,
            "baseline_wander_ratio": 0.02,
            "signal_quality": "质量良好",
        },
        "waveform": {"lead_ii": lead_ii},
        "notes": "当前为 synthetic_normal 模拟正常心电模式，仅用于演示和联调，不用于临床诊断。",
    }
    source_row = {
        "mode": "synthetic_normal",
        "username": "synthetic_normal",
        "create_time": checkup_time,
        "source_xls": None,
    }
    return skill_payload, source_row


class ECGMonitorService:
    """Background task manager for remote ECG monitor -> report flow."""

    def __init__(self):
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

    def _save_task(self, task_id: str, **fields: Any) -> Dict[str, Any]:
        with self._condition:
            task = self._tasks.get(task_id) or {"task_id": task_id}
            task.update(fields)
            task["updated_at"] = _utc_now_iso()
            self._tasks[task_id] = task
            self._condition.notify_all()
            return dict(task)

    def _get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task else None

    def start_monitor(
        self,
        session_id: str,
        tenant_id: str,
        user_id: str,
        intake: ECGMonitorStartRequest,
    ) -> ECGMonitorStartResponse:
        task_id = str(uuid.uuid4())
        now = _utc_now_iso()
        monitor_mode = _resolve_monitor_mode(intake.monitor_data_mode)
        queued_message = (
            "任务已创建，准备生成模拟正常心电数据。"
            if monitor_mode == "synthetic_normal"
            else "任务已创建，准备连接ECG站点抓取指定时间点数据。"
        )
        self._save_task(
            task_id,
            status="queued",
            message=queued_message,
            started_at=now,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            report=None,
            source_row=None,
            success=False,
        )

        # Persist user-supplied baseline info early so next chat can reuse it.
        try:
            update_profile(
                session_id,
                {
                    "basic_info": {
                        "age": intake.age,
                        "gender": _normalize_profile_gender(intake.gender),
                        "height_cm": _safe_int(intake.height_cm),
                        "weight_kg": _safe_int(intake.weight_kg),
                    },
                    "preferences": {"preferred_name": intake.patient_name},
                },
                tenant_id=tenant_id,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("Failed to persist ECG intake profile: %s", exc)

        thread = threading.Thread(
            target=self._worker,
            args=(task_id, session_id, tenant_id, user_id, intake.model_dump()),
            daemon=True,
        )
        thread.start()

        return ECGMonitorStartResponse(
            task_id=task_id,
            status="queued",
            message=(
                "已开始模拟流程。系统将使用 synthetic_normal 模拟数据生成 ECG 报告。"
                if monitor_mode == "synthetic_normal"
                else "已开始抓取流程。请确认ECG数据已上传云端，系统将按固定时间点抓取并生成报告。"
            ),
            success=True,
        )

    def get_status(
        self,
        task_id: str,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
    ) -> Optional[ECGMonitorStatusResponse]:
        task = self._get_task(task_id)
        if not task:
            return None
        if (
            task.get("tenant_id") != tenant_id
            or task.get("user_id") != user_id
            or task.get("session_id") != session_id
        ):
            return None
        return ECGMonitorStatusResponse(
            task_id=task_id,
            status=task.get("status", "unknown"),
            message=task.get("message", ""),
            started_at=task.get("started_at"),
            updated_at=task.get("updated_at"),
            report=task.get("report"),
            llm_input=task.get("llm_input"),
            llm_output=task.get("llm_output"),
            source_row=task.get("source_row"),
            success=bool(task.get("success", False)),
        )

    def wait_for_status_update(
        self,
        task_id: str,
        *,
        tenant_id: str,
        user_id: str,
        session_id: str,
        last_updated_at: str | None,
        timeout_sec: float = 15.0,
    ) -> Optional[ECGMonitorStatusResponse]:
        def _has_update() -> bool:
            task = self._tasks.get(task_id)
            if not task:
                return False
            if (
                task.get("tenant_id") != tenant_id
                or task.get("user_id") != user_id
                or task.get("session_id") != session_id
            ):
                return False
            return bool(task.get("updated_at")) and task.get("updated_at") != last_updated_at

        with self._condition:
            ready = self._condition.wait_for(_has_update, timeout=timeout_sec)
            if not ready:
                return None
            task = dict(self._tasks.get(task_id) or {})

        return ECGMonitorStatusResponse(
            task_id=task_id,
            status=task.get("status", "unknown"),
            message=task.get("message", ""),
            started_at=task.get("started_at"),
            updated_at=task.get("updated_at"),
            report=task.get("report"),
            llm_input=task.get("llm_input"),
            llm_output=task.get("llm_output"),
            source_row=task.get("source_row"),
            success=bool(task.get("success", False)),
        )

    def _worker(
        self,
        task_id: str,
        session_id: str,
        tenant_id: str,
        user_id: str,
        intake_data: Dict[str, Any],
    ) -> None:
        try:
            intake = ECGMonitorStartRequest.model_validate(intake_data)
            monitor_mode = _resolve_monitor_mode(intake.monitor_data_mode)
            target_create_time = (ECG_MONITOR_TARGET_CREATE_TIME or "").strip()

            self._save_task(
                task_id,
                status="running",
                message=(
                    "正在生成模拟正常心电数据..."
                    if monitor_mode == "synthetic_normal"
                    else "正在登录ECG医生系统..."
                ),
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
            source_row: Dict[str, Any] = {}
            if monitor_mode == "synthetic_normal":
                skill_payload, source_row = _build_synthetic_normal_payload(
                    intake,
                    target_create_time=target_create_time,
                )
            else:
                module = _load_hardware_fetch_module()
                output_dir = Path(os.getenv("ECG_MONITOR_OUTPUT_DIR") or _default_output_dir())
                output_dir.mkdir(parents=True, exist_ok=True)

                cfg = module.LoginConfig(
                    base_url=_normalize_site_base_url(intake.monitor_url or ECG_SITE_URL),
                    username=intake.monitor_username or ECG_SITE_USER,
                    password=intake.monitor_password or ECG_SITE_PASS,
                    timeout_sec=intake.http_timeout_sec,
                    max_login_attempts=intake.max_login_attempts,
                )
                client = module.ECGWebClient(cfg)
                client.login()

                if target_create_time:
                    latest_row = client.get_row_by_create_time(target_create_time)
                    capture_message = (
                        f"已连接成功，正在抓取指定 ECG 数据（createTime={target_create_time}）。"
                    )
                else:
                    latest_row = client.get_latest_row()
                    capture_message = "已连接成功，正在抓取网站最新一条ECG数据。"
                self._save_task(
                    task_id,
                    status="running",
                    message=capture_message,
                )

                self._save_task(task_id, status="running", message="正在下载并解析目标ECG数据...")
                xls_path = client.download_latest_xls(latest_row, output_dir)
                parsed_xls = module.parse_xls_file(xls_path)
                record = module.build_record(
                    latest_row,
                    parsed_xls,
                    xls_path,
                    sample_rate_hz=intake.sample_rate_hz,
                )
                skill_payload = dict(record.get("skill_request") or {})
                parsed_leads = dict(parsed_xls.get("leads") or {})
                lead_ii = (
                    parsed_leads.get("Lead_2")
                    or parsed_leads.get("Lead_11")
                    or parsed_leads.get("Lead_1")
                    or []
                )
                if lead_ii:
                    skill_payload["waveform"] = {"lead_ii": lead_ii[:5000]}
                source_row = {
                    "mode": "live",
                    "username": latest_row.get("username"),
                    "create_time": latest_row.get("createTime"),
                    "source_xls": str(xls_path),
                }

            payload_patient_info = dict(skill_payload.get("patient_info") or {})
            payload_patient_info["patient_id"] = intake.patient_id or payload_patient_info.get("patient_id")
            payload_patient_info["patient_name"] = intake.patient_name
            payload_patient_info["age"] = intake.age
            payload_patient_info["gender"] = intake.gender
            payload_patient_info["height_cm"] = (
                _safe_float(intake.height_cm)
                if intake.height_cm is not None
                else payload_patient_info.get("height_cm")
            )
            payload_patient_info["weight_kg"] = (
                _safe_float(intake.weight_kg)
                if intake.weight_kg is not None
                else payload_patient_info.get("weight_kg")
            )
            skill_payload["patient_info"] = payload_patient_info

            note_parts = []
            if skill_payload.get("notes"):
                note_parts.append(str(skill_payload.get("notes")))
            note_parts.append(f"前端补充患者姓名: {intake.patient_name}")
            skill_payload["notes"] = "；".join(part for part in note_parts if part)
            llm_input_payload = _build_llm_io_payload(skill_payload)

            self._save_task(task_id, status="running", message="正在生成ECG专家报告...")
            ecg_request = ECGReportRequest.model_validate(skill_payload)
            report = ecg_report_service.generate_report(
                ecg_request,
                session_id=session_id,
                tenant_id=tenant_id,
                user_id=user_id,
            )
            llm_output_payload = _build_llm_io_payload(skill_payload, report_text=report.report)

            self._save_task(
                task_id,
                status="completed",
                success=True,
                message=(
                    "已使用 synthetic_normal 模拟正常心电数据生成 ECG 专家报告。"
                    if monitor_mode == "synthetic_normal"
                    else (
                        "已使用网站指定时间点数据生成ECG专家报告。"
                        if target_create_time
                        else "已使用网站最新一条数据生成ECG专家报告。"
                    )
                ),
                report=report.model_dump(),
                llm_input=llm_input_payload,
                llm_output=llm_output_payload,
                source_row=source_row,
            )
        except Exception as exc:
            logger.exception("ECG monitor task failed: %s", exc)
            self._save_task(
                task_id,
                status="failed",
                success=False,
                message=f"ECG报告任务失败: {exc}",
            )


ecg_monitor_service = ECGMonitorService()
