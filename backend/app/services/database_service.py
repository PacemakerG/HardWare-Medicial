"""
MediGenius — services/database_service.py
DatabaseService: all CRUD operations for chat history.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import delete, desc, func, select, text
from sqlalchemy.orm import Session

from app.core.logging_config import logger
from app.db.session import SessionLocal, engine
from app.models.ecg_report import ECGReport
from app.models.message import Base, ContextCheckpoint, Message
from app.models.user import User


class DatabaseService:
    """All database CRUD operations for chat history."""

    def __init__(self, session_local=None, engine_instance=None):
        self.SessionLocal = session_local or SessionLocal
        self.engine = engine_instance or engine
        logger.info("DatabaseService initialized")

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        logger.info("Initializing database tables...")
        self._migrate_legacy_identity_schema()
        Base.metadata.create_all(bind=self.engine)

    def _migrate_legacy_identity_schema(self) -> None:
        """Collapse legacy tenant-scoped SQLite tables to user/session scope."""
        if self.engine.dialect.name != "sqlite":
            return

        with self.engine.begin() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table'")
                ).fetchall()
            }

            def columns(table_name: str) -> set[str]:
                return {
                    row[1]
                    for row in conn.execute(
                        text(f"PRAGMA table_info({table_name})")
                    ).fetchall()
                }

            if "messages" in tables and "tenant_id" in columns("messages"):
                user_expr = (
                    "COALESCE(NULLIF(TRIM(user_id), ''), 'anonymous')"
                    if "user_id" in columns("messages")
                    else "'anonymous'"
                )
                conn.execute(
                    text(
                        "CREATE TABLE messages_user_scope ("
                        "id INTEGER NOT NULL PRIMARY KEY, "
                        "user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous', "
                        "session_id VARCHAR(255) NOT NULL, role VARCHAR(50) NOT NULL, "
                        "content TEXT NOT NULL, source VARCHAR(255), timestamp DATETIME NOT NULL)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO messages_user_scope "
                        "(id, user_id, session_id, role, content, source, timestamp) "
                        f"SELECT id, {user_expr}, session_id, role, content, source, timestamp "
                        "FROM messages"
                    )
                )
                conn.execute(text("DROP TABLE messages"))
                conn.execute(text("ALTER TABLE messages_user_scope RENAME TO messages"))
                conn.execute(text("CREATE INDEX ix_messages_user_id ON messages(user_id)"))
                conn.execute(text("CREATE INDEX ix_messages_session_id ON messages(session_id)"))

            if "ecg_reports" in tables and "tenant_id" in columns("ecg_reports"):
                user_expr = (
                    "COALESCE(NULLIF(TRIM(user_id), ''), 'anonymous')"
                    if "user_id" in columns("ecg_reports")
                    else "'anonymous'"
                )
                conn.execute(
                    text(
                        "CREATE TABLE ecg_reports_user_scope ("
                        "report_id VARCHAR(64) NOT NULL PRIMARY KEY, "
                        "user_id VARCHAR(128) NOT NULL DEFAULT 'anonymous', "
                        "session_id VARCHAR(255), patient_id VARCHAR(255), "
                        "risk_level VARCHAR(32) NOT NULL, report TEXT NOT NULL, "
                        "key_findings TEXT NOT NULL, recommendations TEXT NOT NULL, "
                        "disclaimer TEXT NOT NULL, raw_request TEXT NOT NULL, "
                        "created_at DATETIME NOT NULL)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT INTO ecg_reports_user_scope "
                        "(report_id, user_id, session_id, patient_id, risk_level, report, "
                        "key_findings, recommendations, disclaimer, raw_request, created_at) "
                        f"SELECT report_id, {user_expr}, session_id, patient_id, risk_level, "
                        "report, key_findings, recommendations, disclaimer, raw_request, created_at "
                        "FROM ecg_reports"
                    )
                )
                conn.execute(text("DROP TABLE ecg_reports"))
                conn.execute(
                    text("ALTER TABLE ecg_reports_user_scope RENAME TO ecg_reports")
                )
                conn.execute(
                    text("CREATE INDEX ix_ecg_reports_user_id ON ecg_reports(user_id)")
                )
                conn.execute(
                    text("CREATE INDEX ix_ecg_reports_session_id ON ecg_reports(session_id)")
                )
                conn.execute(
                    text("CREATE INDEX ix_ecg_reports_patient_id ON ecg_reports(patient_id)")
                )

            if "users" in tables and "tenant_id" in columns("users"):
                conn.execute(
                    text(
                        "CREATE TABLE users_user_scope ("
                        "id INTEGER NOT NULL PRIMARY KEY, user_id VARCHAR(128) NOT NULL UNIQUE, "
                        "password_hash VARCHAR(512) NOT NULL, role VARCHAR(64) NOT NULL, "
                        "is_active BOOLEAN NOT NULL, created_at DATETIME NOT NULL, "
                        "last_login_at DATETIME)"
                    )
                )
                conn.execute(
                    text(
                        "INSERT OR IGNORE INTO users_user_scope "
                        "(id, user_id, password_hash, role, is_active, created_at, last_login_at) "
                        "SELECT id, user_id, password_hash, role, is_active, created_at, "
                        "last_login_at FROM users ORDER BY id"
                    )
                )
                conn.execute(text("DROP TABLE users"))
                conn.execute(text("ALTER TABLE users_user_scope RENAME TO users"))
                conn.execute(text("CREATE UNIQUE INDEX ix_users_user_id ON users(user_id)"))

    def get_session(self) -> Session:
        return self.SessionLocal()

    def ensure_user_table(self) -> None:
        """Create the users table when legacy startup hooks were skipped/mocked."""
        User.__table__.create(bind=self.engine, checkfirst=True)

    def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        source: Optional[str] = None,
        user_id: str = "anonymous",
    ) -> int:
        logger.debug("Saving %s message for session %s...", role, session_id[:8])
        with self.get_session() as session:
            message = Message(
                user_id=user_id,
                session_id=session_id,
                role=role,
                content=content,
                source=source,
            )
            session.add(message)
            session.flush()
            message_id = int(message.id)
            session.commit()
            return message_id

    def get_chat_history(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
    ) -> List[Dict]:
        with self.get_session() as session:
            stmt = (
                select(Message)
                .where(Message.session_id == session_id)
                .where(Message.user_id == user_id)
                .order_by(Message.timestamp)
            )
            return [msg.to_dict() for msg in session.execute(stmt).scalars().all()]

    def get_chat_history_after(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
        after_message_id: int = 0,
        before_message_id: Optional[int] = None,
    ) -> List[Dict]:
        """Load only uncompacted messages, optionally excluding the current turn."""
        with self.get_session() as session:
            stmt = (
                select(Message)
                .where(Message.session_id == session_id)
                .where(Message.user_id == user_id)
                .where(Message.id > max(0, int(after_message_id)))
            )
            if before_message_id is not None:
                stmt = stmt.where(Message.id < int(before_message_id))
            stmt = stmt.order_by(Message.id)
            return [msg.to_dict() for msg in session.execute(stmt).scalars().all()]

    def get_context_checkpoint(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
    ) -> Optional[Dict]:
        with self.get_session() as session:
            stmt = (
                select(ContextCheckpoint)
                .where(ContextCheckpoint.session_id == session_id)
                .where(ContextCheckpoint.user_id == user_id)
            )
            checkpoint = session.execute(stmt).scalar_one_or_none()
            if checkpoint is None:
                return None
            try:
                facts = json.loads(checkpoint.medical_facts_json or "[]")
            except Exception:
                facts = []
            return {
                "summary_text": checkpoint.summary_text or "",
                "medical_facts": facts if isinstance(facts, list) else [],
                "covered_message_id": int(checkpoint.covered_message_id or 0),
                "version": int(checkpoint.version or 1),
            }

    def save_context_checkpoint(
        self,
        session_id: str,
        *,
        user_id: str,
        summary_text: str,
        medical_facts: List[Dict],
        covered_message_id: int,
    ) -> Dict:
        with self.get_session() as session:
            stmt = (
                select(ContextCheckpoint)
                .where(ContextCheckpoint.session_id == session_id)
                .where(ContextCheckpoint.user_id == user_id)
            )
            checkpoint = session.execute(stmt).scalar_one_or_none()
            if checkpoint is None:
                checkpoint = ContextCheckpoint(
                    user_id=user_id,
                    session_id=session_id,
                    version=1,
                )
                session.add(checkpoint)
            else:
                checkpoint.version = int(checkpoint.version or 0) + 1

            checkpoint.summary_text = summary_text
            checkpoint.medical_facts_json = json.dumps(
                medical_facts,
                ensure_ascii=False,
            )
            checkpoint.covered_message_id = int(covered_message_id)
            session.commit()
            return {
                "covered_message_id": checkpoint.covered_message_id,
                "version": checkpoint.version,
            }

    def get_all_sessions(
        self,
        *,
        user_id: str = "anonymous",
    ) -> List[Dict]:
        with self.get_session() as session:
            latest_sub = (
                select(
                    Message.session_id,
                    func.max(Message.timestamp).label("max_ts"),
                )
                .where(Message.role == "user")
                .where(Message.user_id == user_id)
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
                .where(Message.user_id == user_id)
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

    def delete_session(
        self,
        session_id: str,
        *,
        user_id: str = "anonymous",
    ) -> None:
        logger.info("Deleting session %s...", session_id[:8])
        with self.get_session() as session:
            session.execute(
                delete(Message)
                .where(Message.session_id == session_id)
                .where(Message.user_id == user_id)
            )
            session.execute(
                delete(ECGReport)
                .where(ECGReport.session_id == session_id)
                .where(ECGReport.user_id == user_id)
            )
            session.execute(
                delete(ContextCheckpoint)
                .where(ContextCheckpoint.session_id == session_id)
                .where(ContextCheckpoint.user_id == user_id)
            )
            session.commit()

    def save_ecg_report(
        self,
        session_id: Optional[str],
        user_id: str,
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
                user_id=user_id,
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

    def get_ecg_report(
        self,
        report_id: str,
        *,
        user_id: str = "anonymous",
    ) -> Optional[Dict]:
        with self.get_session() as session:
            stmt = (
                select(ECGReport)
                .where(ECGReport.report_id == report_id)
                .where(ECGReport.user_id == user_id)
            )
            record = session.execute(stmt).scalar_one_or_none()
            return record.to_dict() if record else None

    def get_user(self, user_id: str) -> Optional[User]:
        with self.get_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            return session.execute(stmt).scalar_one_or_none()

    def create_user(
        self,
        *,
        user_id: str,
        password_hash: str,
        role: str = "user",
    ) -> Dict:
        with self.get_session() as session:
            record = User(
                user_id=user_id,
                password_hash=password_hash,
                role=role,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record.to_dict()

    def update_user_last_login(self, user_id: str) -> None:
        with self.get_session() as session:
            stmt = select(User).where(User.user_id == user_id)
            record = session.execute(stmt).scalar_one_or_none()
            if not record:
                return
            record.last_login_at = datetime.utcnow()
            session.commit()


# Module-level singleton
db_service = DatabaseService()
