"""
MediGenius — schemas/ecg.py
Pydantic schemas for ECG report generation skill.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ECGPatientInfo(BaseModel):
    patient_id: Optional[str] = None
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
    notes: Optional[str] = None


class ECGReportResponse(BaseModel):
    report_id: Optional[str] = None
    created_at: Optional[str] = None
    report: str
    risk_level: str
    key_findings: List[str]
    recommendations: List[str]
    disclaimer: str
    success: bool
