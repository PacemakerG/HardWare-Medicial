"""
MediGenius — agents/memory.py
Memory agents:
  - MemoryReadAgent: trim recent history + load profile context
  - MemoryWriteAsyncAgent: async profile update after final answer
"""

from app.core.state import AgentState
from app.services.profile_service import (
    load_profile,
    render_profile_as_text,
    schedule_profile_update,
)


def MemoryReadAgent(state: AgentState) -> AgentState:
    """Trim history and load persistent profile context into state."""
    history = state.get("conversation_history", [])
    if len(history) > 20:
        history = history[-20:]
    state["conversation_history"] = history

    session_id = state.get("session_id", "")
    tenant_id = state.get("tenant_id", "default")
    user_id = state.get("user_id", "anonymous")
    profile = load_profile(
        session_id,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    state["memory_context"] = render_profile_as_text(profile)
    state["user_preferences"] = profile.get("preferences") or {}

    return state


def MemoryWriteAsyncAgent(state: AgentState) -> AgentState:
    """Schedule asynchronous profile updates without blocking main response path."""
    session_id = state.get("session_id", "")
    tenant_id = state.get("tenant_id", "default")
    user_id = state.get("user_id", "anonymous")
    question = state.get("question", "")
    answer = state.get("generation", "")

    if session_id and question and answer:
        schedule_profile_update(
            session_id,
            question,
            answer,
            tenant_id=tenant_id,
            user_id=user_id,
        )

    return state


# Backward-compatible alias
MemoryAgent = MemoryReadAgent
