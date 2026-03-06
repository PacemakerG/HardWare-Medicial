"""
MediGenius — core/langgraph_workflow.py
LangGraph StateGraph definition, routing functions, and workflow factory.
"""

from langgraph.graph import END, StateGraph

from app.agents.executor import ExecutorAgent
from app.agents.judge_need_rag import JudgeNeedRAGAgent
from app.agents.memory import MemoryReadAgent, MemoryWriteAsyncAgent
from app.agents.planner import KeywordRouterAgent
from app.agents.retriever import RetrieverAgent
from app.core.state import AgentState


# ── Routing Functions ──────────────────────────────────────────────────────────
def _route_after_keyword_router(state: AgentState) -> str:
    return "rag" if state.get("use_rag") else "judge_need_rag"


def _route_after_judge_need_rag(state: AgentState) -> str:
    return "rag" if state.get("need_rag") else "executor"


# ── Workflow Factory ───────────────────────────────────────────────────────────
def create_workflow():
    """Build and compile the refactored workflow with a single executor sink."""
    workflow = StateGraph(AgentState)

    # Register nodes
    workflow.add_node("memory_read", MemoryReadAgent)
    workflow.add_node("keyword_router", KeywordRouterAgent)
    workflow.add_node("judge_need_rag", JudgeNeedRAGAgent)
    workflow.add_node("rag", RetrieverAgent)
    workflow.add_node("executor", ExecutorAgent)
    workflow.add_node("memory_write_async", MemoryWriteAsyncAgent)

    # Entry point
    workflow.set_entry_point("memory_read")

    # Edges
    workflow.add_edge("memory_read", "keyword_router")
    workflow.add_conditional_edges(
        "keyword_router",
        _route_after_keyword_router,
        {"rag": "rag", "judge_need_rag": "judge_need_rag"},
    )
    workflow.add_conditional_edges(
        "judge_need_rag",
        _route_after_judge_need_rag,
        {"rag": "rag", "executor": "executor"},
    )
    workflow.add_edge("rag", "executor")
    workflow.add_edge("executor", "memory_write_async")
    workflow.add_edge("memory_write_async", END)

    return workflow.compile()
