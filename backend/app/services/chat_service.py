"""
MediGenius — services/chat_service.py
ChatService: orchestrates the LangGraph agentic workflow for each chat message.
"""

from datetime import datetime
from typing import Any, Dict

from app.core.langgraph_workflow import create_workflow
from app.core.logging_config import logger
from app.core.state import initialize_conversation_state, reset_query_state
from app.services.database_service import db_service
from app.services.flow_trace_service import append_flow_trace_record


class ChatService:
    """Orchestrates the agentic workflow for each chat message."""

    def __init__(self):
        self.workflow_app = None
        self.conversation_states: Dict[str, Dict] = {}
        logger.info("ChatService initialized")

    def initialize_workflow(self) -> None:
        """Compile and cache the LangGraph workflow (called once at startup)."""
        if not self.workflow_app:
            logger.info("Initializing LangGraph workflow...")
            self.workflow_app = create_workflow()
            logger.info("LangGraph workflow initialized successfully")

    def _load_persisted_history(self, session_id: str) -> list[dict]:
        """Bootstrap in-memory conversation history from persisted chat records."""
        history = db_service.get_chat_history(session_id)
        restored = []
        for item in history[-20:]:
            record = {
                "role": item.get("role", ""),
                "content": item.get("content", ""),
            }
            if item.get("source"):
                record["source"] = item["source"]
            restored.append(record)
        return restored

    async def process_message(self, session_id: str, message: str) -> Dict[str, Any]:
        """Run the agentic pipeline for a single user message."""
        logger.info("Processing message for session %s...", session_id[:8])

        if not self.workflow_app:
            raise ValueError("Workflow not initialized")

        # Persist user message
        db_service.save_message(session_id, "user", message)

        # Initialize or retrieve conversation state
        if session_id not in self.conversation_states:
            state = initialize_conversation_state()
            state["conversation_history"] = self._load_persisted_history(session_id)
            self.conversation_states[session_id] = state

        state = self.conversation_states[session_id]
        state = reset_query_state(state)
        state["session_id"] = session_id
        state["question"] = message

        # Run workflow (async preferred, sync fallback)
        try:
            result = await self.workflow_app.ainvoke(state)
        except AttributeError:
            logger.warning("Falling back to sync invoke")
            result = self.workflow_app.invoke(state)

        self.conversation_states[session_id].update(result)

        response_text = result.get("generation", "Unable to generate response.")
        source = result.get("source", "Unknown")
        flow_trace = result.get("flow_trace", [])

        # Persist assistant response
        db_service.save_message(session_id, "assistant", response_text, source)
        append_flow_trace_record(
            session_id=session_id,
            question=message,
            flow_trace=flow_trace,
            source=source,
            safety_level=result.get("safety_level", "SAFE"),
            domain=result.get("domain", "general"),
            primary_department=result.get("primary_department", "") or "",
            use_rag=bool(result.get("use_rag", False)),
            need_rag=bool(result.get("need_rag", False)),
        )

        return {
            "response": response_text,
            "source": source,
            "timestamp": datetime.now().strftime("%I:%M %p"),
            "success": bool(result.get("generation")),
            "flow_trace": flow_trace,
        }

    def clear_conversation(self, session_id: str) -> None:
        """Reset the in-memory conversation state for a session."""
        if session_id in self.conversation_states:
            self.conversation_states[session_id] = initialize_conversation_state()
            logger.info("Conversation cleared for session %s", session_id[:8])


# Module-level singleton
chat_service = ChatService()
