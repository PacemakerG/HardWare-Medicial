"""
MediGenius — core/state.py
AgentState TypedDict and state helper functions.
"""

from typing import Dict, List, Optional, TypedDict

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
    retrieval_query: Optional[str]
    primary_department: Optional[str]
    department_candidates: List[Dict]
    department_queries: Dict[str, str]
    retrieval_scopes: List[str]
    retrieval_results_by_scope: Dict[str, List[Dict]]
    merged_rag_context: List[Dict]
    reranked_rag_context: List[Dict]
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
        "retrieval_query": None,
        "primary_department": None,
        "department_candidates": [],
        "department_queries": {},
        "retrieval_scopes": [],
        "retrieval_results_by_scope": {},
        "merged_rag_context": [],
        "reranked_rag_context": [],
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
            "retrieval_query": None,
            "primary_department": None,
            "department_candidates": [],
            "department_queries": {},
            "retrieval_scopes": [],
            "retrieval_results_by_scope": {},
            "merged_rag_context": [],
            "reranked_rag_context": [],
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
        }
    )
    return state


def append_flow_trace(state: AgentState, node_name: str) -> AgentState:
    """Append a workflow node name to the trace path."""
    state.setdefault("flow_trace", [])
    state["flow_trace"].append(node_name)
    return state
