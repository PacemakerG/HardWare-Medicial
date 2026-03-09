"""
MediGenius — agents/memory.py
Memory agents:
  - MemoryReadAgent: trim recent history + load profile context
  - MemoryWriteAsyncAgent: async profile update after final answer
"""

from app.core.state import AgentState, append_flow_trace
from app.services.profile_service import (
    load_profile,
    render_profile_as_text,
    schedule_profile_update,
)


def MemoryReadAgent(state: AgentState) -> AgentState:
    """Trim history and load persistent profile context into state."""
    append_flow_trace(state, "memory_read")
    history = state.get("conversation_history", [])
    if len(history) > 20:
        history = history[-20:]
    state["conversation_history"] = history

    session_id = state.get("session_id", "")
    profile = load_profile(session_id)
    state["memory_context"] = render_profile_as_text(profile)

    return state


def MemoryWriteAsyncAgent(state: AgentState) -> AgentState:
    """Schedule asynchronous profile updates without blocking main response path."""
    append_flow_trace(state, "memory_write_async")
    session_id = state.get("session_id", "")
    question = state.get("question", "")
    answer = state.get("generation", "")

    if session_id and question and answer:
        schedule_profile_update(session_id, question, answer)

    return state


# Backward-compatible alias
MemoryAgent = MemoryReadAgent
