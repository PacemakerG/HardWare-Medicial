"""
MediGenius — schemas/ecg.py
Pydantic schemas for ECG report generation skill.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.config import ECG_SITE_URL

class ECGPatientInfo(BaseModel):
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    age: Optional[int] = Field(default=None, ge=0, le=130)
    gender: Optional[str] = None
    height_cm: Optional[float] = Field(default=None, gt=0, le=260)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=500)
    checkup_time: Optional[str] = None


class ECGReportRequest(BaseModel):
    patient_info: ECGPatientInfo
    diagnosis_codes: List[str] = Field(default_factory=list)
    diagnosis_cn: List[str] = Field(default_factory=list)
    signal_quality: Optional[str] = "未知"
    features: Dict[str, Any] = Field(default_factory=dict)
    waveform: Dict[str, List[float]] = Field(default_factory=dict)
    notes: Optional[str] = None


class ECGReportResponse(BaseModel):
    report_id: Optional[str] = None
    created_at: Optional[str] = None
    report: str
    risk_level: str
    key_findings: List[str]
    recommendations: List[str]
    disclaimer: str
    pdf_url: Optional[str] = None
    success: bool


class ECGMonitorStartRequest(BaseModel):
    patient_name: str = Field(min_length=1, max_length=80)
    age: int = Field(ge=0, le=130)
    gender: str = Field(min_length=1, max_length=20)
    patient_id: Optional[str] = Field(default=None, max_length=64)
    height_cm: Optional[float] = Field(default=None, gt=0, le=260)
    weight_kg: Optional[float] = Field(default=None, gt=0, le=500)

    monitor_url: Optional[str] = Field(
        default=ECG_SITE_URL,
        max_length=300,
    )
    monitor_username: Optional[str] = Field(default=None, max_length=128)
    monitor_password: Optional[str] = Field(default=None, max_length=128)
    monitor_data_mode: Optional[str] = Field(default=None, max_length=32)
    wait_timeout_sec: int = Field(default=60, ge=30, le=1800)
    poll_interval_sec: int = Field(default=5, ge=2, le=60)
    http_timeout_sec: int = Field(default=15, ge=5, le=120)
    max_login_attempts: int = Field(default=80, ge=5, le=300)
    sample_rate_hz: int = Field(default=500, ge=100, le=2000)


class ECGMonitorStartResponse(BaseModel):
    task_id: str
    status: str
    message: str
    success: bool


class ECGMonitorStatusResponse(BaseModel):
    task_id: str
    status: str
    message: str
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    report: Optional[ECGReportResponse] = None
    llm_input: Optional[Dict[str, Any]] = None
    llm_output: Optional[Dict[str, Any]] = None
    source_row: Optional[Dict[str, Any]] = None
    success: bool
