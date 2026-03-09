"""Tests for LangGraph routing functions"""
from app.core.langgraph_workflow import (
    _route_after_judge_need_rag,
    _route_after_keyword_router,
    _route_after_medical_router,
    create_workflow,
)


def test_route_after_keyword_router():
    assert _route_after_keyword_router({"domain": "medical", "use_rag": True}) == "medical_router"
    assert _route_after_keyword_router({"domain": "nutrition", "use_rag": True}) == "query_rewriter"
    assert _route_after_keyword_router({"use_rag": False}) == "judge_need_rag"


def test_route_after_judge_need_rag():
    assert _route_after_judge_need_rag({"need_rag": True}) == "query_rewriter"
    assert _route_after_judge_need_rag({"need_rag": False}) == "executor"


def test_route_after_medical_router():
    assert _route_after_medical_router({"use_rag": True}) == "query_rewriter"
    assert _route_after_medical_router({"use_rag": False}) == "executor"


def test_create_workflow():
    workflow = create_workflow()
    assert workflow is not None
