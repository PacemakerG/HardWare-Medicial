"""
MediGenius — services/chat_service.py
ChatService: orchestrates the LangGraph agentic workflow for each chat message.
"""

from datetime import datetime
from typing import Any, Dict
import threading

from app.core.langgraph_workflow import create_workflow
from app.core.logging_config import logger
from app.core.state import initialize_conversation_state, reset_query_state
from app.services.database_service import db_service


class ChatService:
    """Orchestrates the agentic workflow for each chat message."""

    def __init__(self):
        self.workflow_app = None
        self.conversation_states: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        logger.info("ChatService initialized")

    @staticmethod
    def _context_key(tenant_id: str, user_id: str, session_id: str) -> str:
        return f"{tenant_id}::{user_id}::{session_id}"

    def initialize_workflow(self) -> None:
        """Compile and cache the LangGraph workflow (called once at startup)."""
        if not self.workflow_app:
            logger.info("Initializing LangGraph workflow...")
            self.workflow_app = create_workflow()
            logger.info("LangGraph workflow initialized successfully")

    async def process_message(
        self,
        session_id: str,
        message: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        """Run the agentic pipeline for a single user message."""
        logger.info(
            "Processing message tenant=%s user=%s session=%s...",
            tenant_id,
            user_id,
            session_id[:8],
        )

        if not self.workflow_app:
            raise ValueError("Workflow not initialized")

        # Persist user message
        db_service.save_message(
            session_id,
            "user",
            message,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Initialize or retrieve conversation state
        context_key = self._context_key(tenant_id, user_id, session_id)
        with self._lock:
            if context_key not in self.conversation_states:
                self.conversation_states[context_key] = initialize_conversation_state()
            state = self.conversation_states[context_key]
        state = reset_query_state(state)
        state["tenant_id"] = tenant_id
        state["user_id"] = user_id
        state["session_id"] = session_id
        state["question"] = message

        # Run workflow (async preferred, sync fallback)
        try:
            result = await self.workflow_app.ainvoke(state)
        except AttributeError:
            logger.warning("Falling back to sync invoke")
            result = self.workflow_app.invoke(state)

        with self._lock:
            self.conversation_states[context_key].update(result)

        response_text = result.get("generation", "Unable to generate response.")
        source = result.get("source", "Unknown")

        # Persist assistant response
        db_service.save_message(
            session_id,
            "assistant",
            response_text,
            source,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        return {
            "response": response_text,
            "source": source,
            "timestamp": datetime.now().strftime("%I:%M %p"),
            "success": bool(result.get("generation")),
        }

    def clear_conversation(
        self,
        session_id: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> None:
        """Reset the in-memory conversation state for a session."""
        context_key = self._context_key(tenant_id, user_id, session_id)
        with self._lock:
            if context_key in self.conversation_states:
                self.conversation_states[context_key] = initialize_conversation_state()
                logger.info(
                    "Conversation cleared tenant=%s user=%s session=%s",
                    tenant_id,
                    user_id,
                    session_id[:8],
                )


# Module-level singleton
chat_service = ChatService()
