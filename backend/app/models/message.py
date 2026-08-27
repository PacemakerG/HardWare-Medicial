"""
MediGenius — models/message.py
SQLAlchemy ORM model for chat messages.
"""

from datetime import datetime
from typing import Dict

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Message(Base):
    """Persisted chat message (user or assistant turn)."""

    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, default="anonymous", index=True)
    session_id = Column(String(255), nullable=False, index=True)
    role = Column(String(50), nullable=False)          # "user" | "assistant"
    content = Column(Text, nullable=False)
    source = Column(String(255), nullable=True)        # e.g. "Wikipedia Medical Information"
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class ContextCheckpoint(Base):
    """Incremental conversation compaction state scoped to one user session."""

    __tablename__ = "context_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "session_id",
            name="uq_context_checkpoint_user_session",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(128), nullable=False, default="anonymous", index=True)
    session_id = Column(String(255), nullable=False, index=True)
    summary_text = Column(Text, nullable=False, default="")
    medical_facts_json = Column(Text, nullable=False, default="[]")
    covered_message_id = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
