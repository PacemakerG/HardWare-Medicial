"""Tests for LangGraph workflow routing — Deep Modular Architecture"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.langgraph_workflow import (  # noqa: E402
    _route_after_judge_need_rag,
    _route_after_keyword_router,
)
from app.core.state import initialize_conversation_state  # noqa: E402


def test_routing_logic():
    state = initialize_conversation_state()

    # Keyword router
    state["use_rag"] = True
    assert _route_after_keyword_router(state) == "rag"
    state["use_rag"] = False
    assert _route_after_keyword_router(state) == "judge_need_rag"

    # Judge1 router
    state["need_rag"] = True
    assert _route_after_judge_need_rag(state) == "rag"
    state["need_rag"] = False
    assert _route_after_judge_need_rag(state) == "executor"
