"""
MediGenius — services/ecg_monitor_service.py
Background ECG monitor workflow:
1) Receive basic patient info from frontend.
2) Login remote doctor portal and fetch the latest ECG row immediately.
3) Download + parse latest XLS and convert to ECG skill payload.
4) Generate ECG report and expose task status for frontend polling.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from app.core.config import ECG_SITE_PASS, ECG_SITE_URL, ECG_SITE_USER
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
        self._save_task(
            task_id,
            status="queued",
            message="任务已创建，准备连接ECG站点抓取最新数据。",
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
            message="已开始抓取流程。请确认ECG数据已上传云端，系统将直接使用最新一条生成报告。",
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
            self._save_task(
                task_id,
                status="running",
                message="正在登录ECG医生系统...",
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
            )
            intake = ECGMonitorStartRequest.model_validate(intake_data)

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

            latest_row = client.get_latest_row()
            self._save_task(
                task_id,
                status="running",
                message="已连接成功，正在抓取网站最新一条ECG数据。",
            )

            self._save_task(task_id, status="running", message="正在下载并解析最新ECG数据...")
            xls_path = client.download_latest_xls(latest_row, output_dir)
            parsed_xls = module.parse_xls_file(xls_path)
            record = module.build_record(
                latest_row,
                parsed_xls,
                xls_path,
                sample_rate_hz=intake.sample_rate_hz,
            )

            skill_payload = dict(record.get("skill_request") or {})
            payload_patient_info = dict(skill_payload.get("patient_info") or {})
            payload_patient_info["patient_id"] = intake.patient_id or payload_patient_info.get(
                "patient_id"
            )
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
            parsed_leads = dict(parsed_xls.get("leads") or {})
            lead_ii = (
                parsed_leads.get("Lead_2")
                or parsed_leads.get("Lead_11")
                or parsed_leads.get("Lead_1")
                or []
            )
            if lead_ii:
                skill_payload["waveform"] = {"lead_ii": lead_ii[:5000]}

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
                message="已使用网站最新一条数据生成ECG专家报告。",
                report=report.model_dump(),
                llm_input=llm_input_payload,
                llm_output=llm_output_payload,
                source_row={
                    "username": latest_row.get("username"),
                    "create_time": latest_row.get("createTime"),
                    "source_xls": str(xls_path),
                },
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
