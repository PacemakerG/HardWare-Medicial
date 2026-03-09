"""
MediGenius — core/langgraph_workflow.py
LangGraph StateGraph definition, routing functions, and workflow factory.
"""

from langgraph.graph import END, StateGraph

from app.agents.executor import ExecutorAgent
from app.agents.judge_need_rag import JudgeNeedRAGAgent
from app.agents.memory import MemoryReadAgent, MemoryWriteAsyncAgent
from app.agents.medical_router import MedicalRouterAgent
from app.agents.planner import HealthConciergeAgent
from app.agents.query_rewriter import QueryRewriterAgent
from app.agents.retriever import RetrieverAgent
from app.agents.reranker import RerankerAgent
from app.core.state import AgentState


# ── Routing Functions ──────────────────────────────────────────────────────────
def _route_after_concierge(state: AgentState) -> str:
    if state.get("safety_level") in {"EMERGENCY", "CLARIFY"}:
        return "executor"
    if state.get("selected_department_forced"):
        return "query_rewriter"
    if state.get("domain") == "medical":
        return "medical_router"
    if state.get("use_rag"):
        return "query_rewriter"
    return "judge_need_rag"


def _route_after_judge_need_rag(state: AgentState) -> str:
    return "query_rewriter" if state.get("need_rag") else "executor"


def _route_after_medical_router(state: AgentState) -> str:
    return "query_rewriter" if state.get("use_rag") else "executor"


# ── Workflow Factory ───────────────────────────────────────────────────────────
def create_workflow():
    """Build and compile the refactored workflow with a single executor sink."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("memory_read", MemoryReadAgent)
    workflow.add_node("health_concierge", HealthConciergeAgent)
    workflow.add_node("medical_router", MedicalRouterAgent)
    workflow.add_node("judge_need_rag", JudgeNeedRAGAgent)
    workflow.add_node("query_rewriter", QueryRewriterAgent)
    workflow.add_node("rag", RetrieverAgent)
    workflow.add_node("reranker", RerankerAgent)
    workflow.add_node("executor", ExecutorAgent)
    workflow.add_node("memory_write_async", MemoryWriteAsyncAgent)

    # Entry point
    workflow.set_entry_point("memory_read")

    # Edges
    workflow.add_edge("memory_read", "health_concierge")
    workflow.add_conditional_edges(
        "health_concierge",
        _route_after_concierge,
        {
            "executor": "executor",
            "medical_router": "medical_router",
            "query_rewriter": "query_rewriter",
            "judge_need_rag": "judge_need_rag",
        },
    )
    workflow.add_conditional_edges(
        "medical_router",
        _route_after_medical_router,
        {"query_rewriter": "query_rewriter", "executor": "executor"},
    )
    workflow.add_conditional_edges(
        "judge_need_rag",
        _route_after_judge_need_rag,
        {"query_rewriter": "query_rewriter", "executor": "executor"},
    )
    workflow.add_edge("query_rewriter", "rag")
    workflow.add_edge("rag", "reranker")
    workflow.add_edge("reranker", "executor")
    workflow.add_edge("executor", "memory_write_async")
    workflow.add_edge("memory_write_async", END)

    return workflow.compile()


_route_after_keyword_router = _route_after_concierge
