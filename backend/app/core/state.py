"""
MediGenius — core/state.py
AgentState TypedDict and state helper functions.
"""

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Dict, Iterator, List, Optional, TypedDict

from langchain_core.documents import Document


class AgentState(TypedDict):
    """Shared state passed between all LangGraph agent nodes."""

    tenant_id: str
    user_id: str
    session_id: str
    question: str
    documents: List[Document]
    rag_context: List[Dict]
    memory_context: str
    user_preferences: Dict
    generation: str
    source: str
    search_query: Optional[str]
    selected_department: Optional[str]
    selected_department_forced: bool
    retrieval_query: Optional[str]
    retrieval_queries: List[str]
    primary_department: Optional[str]
    department_candidates: List[Dict]
    department_queries: Dict[str, str]
    department_multi_queries: Dict[str, List[str]]
    query_complexity: str
    retrieval_scopes: List[str]
    retrieval_results_by_scope: Dict[str, List[Dict]]
    merged_rag_context: List[Dict]
    reranked_rag_context: List[Dict]
    packed_rag_context: List[Dict]
    routing_reason: str
    rewrite_reason: str
    conversation_history: List[Dict]
    keyword_hit: bool
    use_rag: bool
    need_rag: bool
    tool_calls: List[Dict]
    tool_budget_used: int
    llm_attempted: bool
    llm_success: bool
    rag_attempted: bool
    rag_success: bool
    wiki_attempted: bool
    wiki_success: bool
    tavily_attempted: bool
    tavily_success: bool
    current_tool: Optional[str]
    retry_count: int
    safety_level: str
    domain: str
    ecg_metrics: str
    flow_trace: List[str]
    profiling: Dict[str, Any]


def initialize_conversation_state() -> AgentState:
    """Return a fresh AgentState with all fields at their defaults."""
    return {
        "tenant_id": "default",
        "user_id": "anonymous",
        "session_id": "",
        "question": "",
        "documents": [],
        "rag_context": [],
        "memory_context": "",
        "user_preferences": {},
        "generation": "",
        "source": "",
        "search_query": None,
        "selected_department": None,
        "selected_department_forced": False,
        "retrieval_query": None,
        "retrieval_queries": [],
        "primary_department": None,
        "department_candidates": [],
        "department_queries": {},
        "department_multi_queries": {},
        "query_complexity": "simple",
        "retrieval_scopes": [],
        "retrieval_results_by_scope": {},
        "merged_rag_context": [],
        "reranked_rag_context": [],
        "packed_rag_context": [],
        "routing_reason": "",
        "rewrite_reason": "",
        "conversation_history": [],
        "keyword_hit": False,
        "use_rag": False,
        "need_rag": False,
        "tool_calls": [],
        "tool_budget_used": 0,
        "llm_attempted": False,
        "llm_success": False,
        "rag_attempted": False,
        "rag_success": False,
        "wiki_attempted": False,
        "wiki_success": False,
        "tavily_attempted": False,
        "tavily_success": False,
        "current_tool": None,
        "retry_count": 0,
        "safety_level": "SAFE",
        "domain": "general",
        "ecg_metrics": "",
        "flow_trace": [],
        "profiling": {
            "node_timings_ms": {},
            "token_usage": {},
            "cost_usd": 0.0,
            "retrieval": {},
        },
    }


def reset_query_state(state: AgentState) -> AgentState:
    """Reset per-query flags while preserving conversation history."""
    state.update(
        {
            "tenant_id": state.get("tenant_id", "default"),
            "user_id": state.get("user_id", "anonymous"),
            "question": "",
            "documents": [],
            "rag_context": [],
            "memory_context": "",
            "user_preferences": {},
            "generation": "",
            "source": "",
            "search_query": None,
            "selected_department": state.get("selected_department"),
            "selected_department_forced": state.get("selected_department_forced", False),
            "retrieval_query": None,
            "retrieval_queries": [],
            "primary_department": None,
            "department_candidates": [],
            "department_queries": {},
            "department_multi_queries": {},
            "query_complexity": "simple",
            "retrieval_scopes": [],
            "retrieval_results_by_scope": {},
            "merged_rag_context": [],
            "reranked_rag_context": [],
            "packed_rag_context": [],
            "routing_reason": "",
            "rewrite_reason": "",
            "keyword_hit": False,
            "use_rag": False,
            "need_rag": False,
            "tool_calls": [],
            "tool_budget_used": 0,
            "llm_attempted": False,
            "llm_success": False,
            "rag_attempted": False,
            "rag_success": False,
            "wiki_attempted": False,
            "wiki_success": False,
            "tavily_attempted": False,
            "tavily_success": False,
            "current_tool": None,
            "retry_count": 0,
            "safety_level": "SAFE",
            "domain": "general",
            "ecg_metrics": "",
            "flow_trace": [],
            "profiling": {
                "node_timings_ms": {},
                "token_usage": {},
                "cost_usd": 0.0,
                "retrieval": {},
            },
        }
    )
    return state


def append_flow_trace(state: AgentState, node_name: str) -> AgentState:
    """Append a workflow node name to the trace path."""
    state.setdefault("flow_trace", [])
    state["flow_trace"].append(node_name)
    return state


def _ensure_profiling_bucket(state: AgentState) -> Dict[str, Any]:
    profiling = state.setdefault("profiling", {})
    if not isinstance(profiling, dict):
        profiling = {}
        state["profiling"] = profiling
    profiling.setdefault("node_timings_ms", {})
    profiling.setdefault("token_usage", {})
    profiling.setdefault("cost_usd", 0.0)
    profiling.setdefault("retrieval", {})
    return profiling


def record_node_timing(state: AgentState, node_name: str, elapsed_ms: float) -> AgentState:
    profiling = _ensure_profiling_bucket(state)
    node_timings = profiling.setdefault("node_timings_ms", {})
    if isinstance(node_timings, dict):
        node_timings[node_name] = round(float(elapsed_ms), 2)
    return state


def set_profile_metric(state: AgentState, key: str, value: Any) -> AgentState:
    profiling = _ensure_profiling_bucket(state)
    profiling[key] = value
    return state


def set_retrieval_metric(state: AgentState, key: str, value: Any) -> AgentState:
    profiling = _ensure_profiling_bucket(state)
    retrieval = profiling.setdefault("retrieval", {})
    if isinstance(retrieval, dict):
        retrieval[key] = value
    return state


def estimate_text_tokens(text: str) -> int:
    """
    Lightweight token estimate used for profiling/cost dashboards.
    Approximation: 1 token ~= 4 chars for mixed zh/en in this project.
    """
    normalized = (text or "").strip()
    if not normalized:
        return 0
    return max(1, int(len(normalized) / 4))


def record_token_usage(
    state: AgentState,
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> AgentState:
    profiling = _ensure_profiling_bucket(state)
    token_usage = profiling.setdefault("token_usage", {})
    if not isinstance(token_usage, dict):
        token_usage = {}
        profiling["token_usage"] = token_usage

    token_usage["prompt_tokens"] = int(token_usage.get("prompt_tokens", 0)) + int(prompt_tokens)
    token_usage["completion_tokens"] = int(token_usage.get("completion_tokens", 0)) + int(
        completion_tokens
    )
    if total_tokens:
        token_usage["total_tokens"] = int(token_usage.get("total_tokens", 0)) + int(total_tokens)
    else:
        token_usage["total_tokens"] = token_usage["prompt_tokens"] + token_usage["completion_tokens"]
    return state


@contextmanager
def profile_node(state: AgentState, node_name: str) -> Iterator[None]:
    started = perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (perf_counter() - started) * 1000.0
        record_node_timing(state, node_name, elapsed_ms)
