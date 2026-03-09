"""
MediGenius — models/ecg_report.py
SQLAlchemy ORM model for persisted ECG reports.
"""

import json
import uuid
from datetime import datetime
from typing import Dict

from sqlalchemy import Column, DateTime, String, Text

from app.models.message import Base


class ECGReport(Base):
    """Persisted ECG report record."""

    __tablename__ = "ecg_reports"

    report_id = Column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id = Column(String(128), nullable=False, default="default", index=True)
    user_id = Column(String(128), nullable=False, default="anonymous", index=True)
    session_id = Column(String(255), nullable=True, index=True)
    patient_id = Column(String(255), nullable=True, index=True)
    risk_level = Column(String(32), nullable=False, default="unknown")
    report = Column(Text, nullable=False)
    key_findings = Column(Text, nullable=False, default="[]")
    recommendations = Column(Text, nullable=False, default="[]")
    disclaimer = Column(Text, nullable=False, default="")
    raw_request = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict:
        return {
            "report_id": self.report_id,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "patient_id": self.patient_id,
            "risk_level": self.risk_level,
            "report": self.report,
            "key_findings": json.loads(self.key_findings or "[]"),
            "recommendations": json.loads(self.recommendations or "[]"),
            "disclaimer": self.disclaimer,
            "raw_request": json.loads(self.raw_request or "{}"),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
