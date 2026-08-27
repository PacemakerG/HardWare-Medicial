"""
MediGenius — agents/memory.py
Memory agents:
  - MemoryReadAgent: compact conversation history + load profile context
  - MemoryWriteAsyncAgent: async profile update after final answer
"""

from app.core.langsmith_service import langsmith_traceable
from app.core.state import (
    AgentState,
    append_flow_trace,
    profile_node,
    set_profile_metric,
)
from app.services.context_compaction_service import context_compaction_service
from app.services.profile_service import (
    load_profile,
    render_profile_as_text,
    schedule_profile_update,
)


@langsmith_traceable("memory_read")
def MemoryReadAgent(state: AgentState) -> AgentState:
    """Synchronously compact history and load persistent profile context."""
    append_flow_trace(state, "memory_read")
    with profile_node(state, "memory_read"):
        history = state.get("conversation_history", [])
        session_id = state.get("session_id", "")
        user_id = state.get("user_id", "anonymous")
        compacted = context_compaction_service.build_context(
            user_id=user_id,
            session_id=session_id,
            current_message_id=state.get("current_message_id"),
            fallback_history=history,
        )
        state.update(compacted)
        state["conversation_history"] = list(compacted.get("recent_history") or [])
        set_profile_metric(
            state,
            "context_compaction",
            compacted.get("context_compression_info") or {},
        )

        profile = load_profile(
            session_id,
            user_id=user_id,
        )
        state["memory_context"] = render_profile_as_text(profile)
        state["user_preferences"] = profile.get("preferences") or {}

    return state


@langsmith_traceable("memory_write_async")
def MemoryWriteAsyncAgent(state: AgentState) -> AgentState:
    """Schedule asynchronous profile updates without blocking main response path."""
    append_flow_trace(state, "memory_write_async")
    with profile_node(state, "memory_write_async"):
        session_id = state.get("session_id", "")
        user_id = state.get("user_id", "anonymous")
        question = state.get("question", "")
        answer = state.get("generation", "")

        if session_id and question and answer:
            schedule_profile_update(
                session_id,
                question,
                answer,
                user_id=user_id,
            )

    return state


# Backward-compatible alias
MemoryAgent = MemoryReadAgent
