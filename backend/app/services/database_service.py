"""
MediGenius — services/database_service.py
DatabaseService: all CRUD operations for chat history.
"""

import json
from typing import Dict, List, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.core.logging_config import logger
from app.db.session import SessionLocal, engine
from app.models.ecg_report import ECGReport
from app.models.message import Base, Message


class DatabaseService:
    """All database CRUD operations for chat history."""

    def __init__(self, session_local=None, engine_instance=None):
        self.SessionLocal = session_local or SessionLocal
        self.engine = engine_instance or engine
        logger.info("DatabaseService initialized")

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        logger.info("Initializing database tables...")
        Base.metadata.create_all(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source: Optional[str] = None,
    ) -> None:
        logger.debug("Saving %s message for session %s...", role, session_id[:8])
        with self.get_session() as session:
            session.add(
                Message(
                    session_id=session_id, role=role, content=content, source=source
                )
            )
            session.commit()

    def get_chat_history(self, session_id: str) -> List[Dict]:
        with self.get_session() as session:
            stmt = (
                select(Message)
                .where(Message.session_id == session_id)
                .order_by(Message.timestamp)
            )
            return [msg.to_dict() for msg in session.execute(stmt).scalars().all()]

    def get_all_sessions(self) -> List[Dict]:
        with self.get_session() as session:
            latest_sub = (
                select(
                    Message.session_id,
                    func.max(Message.timestamp).label("max_ts"),
                )
                .where(Message.role == "user")
                .group_by(Message.session_id)
                .subquery()
            )
            stmt = (
                select(Message.session_id, Message.content, Message.timestamp)
                .join(
                    latest_sub,
                    (Message.session_id == latest_sub.c.session_id)
                    & (Message.timestamp == latest_sub.c.max_ts),
                )
                .order_by(desc(Message.timestamp))
            )
            return [
                {
                    "session_id": row[0],
                    "preview": row[1][:50] + "..." if len(row[1]) > 50 else row[1],
                    "last_active": row[2].isoformat() if row[2] else None,
                }
                for row in session.execute(stmt).all()
            ]

    def delete_session(self, session_id: str) -> None:
        logger.info("Deleting session %s...", session_id[:8])
        with self.get_session() as session:
            session.execute(delete(Message).where(Message.session_id == session_id))
            session.execute(delete(ECGReport).where(ECGReport.session_id == session_id))
            session.commit()

    def save_ecg_report(
        self,
        session_id: Optional[str],
        patient_id: Optional[str],
        risk_level: str,
        report: str,
        key_findings: List[str],
        recommendations: List[str],
        disclaimer: str,
        raw_request: Dict,
    ) -> Dict:
        with self.get_session() as session:
            record = ECGReport(
                session_id=session_id,
                patient_id=patient_id,
                risk_level=risk_level,
                report=report,
                key_findings=json.dumps(key_findings, ensure_ascii=False),
                recommendations=json.dumps(recommendations, ensure_ascii=False),
                disclaimer=disclaimer,
                raw_request=json.dumps(raw_request, ensure_ascii=False),
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.to_dict()

    def get_ecg_report(self, report_id: str) -> Optional[Dict]:
        with self.get_session() as session:
            stmt = select(ECGReport).where(ECGReport.report_id == report_id)
            record = session.execute(stmt).scalar_one_or_none()
            return record.to_dict() if record else None


# Module-level singleton
db_service = DatabaseService()
