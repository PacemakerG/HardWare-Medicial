"""Tests for all agents — Deep Modular Architecture"""
import os
import sys
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.executor import ExecutorAgent  # noqa: E402
from app.agents.memory import MemoryAgent  # noqa: E402
from app.agents.medical_router import MedicalRouterAgent  # noqa: E402
from app.agents.planner import PlannerAgent  # noqa: E402
from app.agents.query_rewriter import QueryRewriterAgent  # noqa: E402
from app.agents.retriever import RetrieverAgent  # noqa: E402
from app.agents.reranker import RerankerAgent  # noqa: E402
from app.core.state import initialize_conversation_state  # noqa: E402


# --- Planner Agent Tests ---
def test_planner_agent_medical():
    state = initialize_conversation_state()
    state["question"] = "我有症状，发烧了，还想问用药问题"
    new_state = PlannerAgent(state)
    assert new_state["current_tool"] == "medical_router"
    assert new_state["domain"] == "medical"


def test_planner_agent_general():
    state = initialize_conversation_state()
    state["question"] = "Hello there"
    new_state = PlannerAgent(state)
    assert new_state["current_tool"] == "judge_need_rag"


# --- Retriever Agent Tests ---
def test_retriever_agent_success():
    state = initialize_conversation_state()
    state["question"] = "fever"
    state["domain"] = "medical"
    state["use_rag"] = True
    state["primary_department"] = "infectious_disease"
    state["department_candidates"] = [{"name": "infectious_disease", "score": 0.9}]
    state["retrieval_query"] = "发热 感染"
    state["department_queries"] = {"infectious_disease": "感染 发热"}

    with patch('app.agents.retriever.get_retriever') as mock_get_retriever:
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = [Document(page_content="Fever details " * 10)]
        mock_get_retriever.return_value = mock_retriever

        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is True
        assert len(new_state["documents"]) > 0
        assert "infectious_disease" in new_state["retrieval_results_by_scope"]


def test_retriever_agent_failure():
    state = initialize_conversation_state()
    state["question"] = "unknown"
    state["domain"] = "medical"
    state["use_rag"] = True
    state["primary_department"] = "hematology"
    state["department_candidates"] = [{"name": "hematology", "score": 0.9}]
    state["retrieval_query"] = "贫血"
    state["department_queries"] = {"hematology": "贫血"}
    with patch('app.agents.retriever.get_retriever') as mock_get:
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = []
        mock_get.return_value = mock_retriever

        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is False


def test_retriever_agent_no_tool():
    state = initialize_conversation_state()
    state["domain"] = "medical"
    state["use_rag"] = True
    state["primary_department"] = "hematology"
    state["department_candidates"] = [{"name": "hematology", "score": 0.9}]
    with patch('app.agents.retriever.get_retriever', return_value=None):
        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is False


def test_medical_router_agent_fallback():
    state = initialize_conversation_state()
    state["question"] = "我血红蛋白低，经常头晕乏力"
    state["domain"] = "medical"
    state["use_rag"] = True
    new_state = MedicalRouterAgent(state)
    assert new_state["primary_department"] == "hematology"
    assert new_state["department_candidates"]


def test_query_rewriter_agent_fallback():
    state = initialize_conversation_state()
    state["question"] = "我血红蛋白低，经常头晕乏力"
    state["domain"] = "medical"
    state["use_rag"] = True
    state["primary_department"] = "hematology"
    state["department_candidates"] = [{"name": "hematology", "score": 0.9}]
    new_state = QueryRewriterAgent(state)
    assert new_state["retrieval_query"]
    assert "hematology" in new_state["department_queries"]


def test_reranker_agent():
    state = initialize_conversation_state()
    state["question"] = "贫血会不会导致头晕"
    state["retrieval_query"] = "贫血 头晕"
    state["primary_department"] = "hematology"
    state["retrieval_scopes"] = ["hematology", "general_medical"]
    state["merged_rag_context"] = [
        {
            "content": "贫血常见症状包括头晕和乏力。",
            "metadata": {"department": "hematology"},
            "scope": "hematology",
            "raw_rank": 0,
        },
        {
            "content": "胃病也可能导致不适。",
            "metadata": {"department": "general_medical"},
            "scope": "general_medical",
            "raw_rank": 1,
        },
    ]
    new_state = RerankerAgent(state)
    assert new_state["rag_context"][0]["scope"] == "hematology"


# --- Memory Agent Tests ---
def test_memory_agent():
    state = initialize_conversation_state()
    state["conversation_history"] = [{"role": "user", "content": str(i)} for i in range(25)]

    new_state = MemoryAgent(state)

    assert len(new_state["conversation_history"]) == 20
    assert new_state["conversation_history"][-1]["content"] == "24"


# --- Executor Agent Tests ---
def test_executor_agent_with_docs():
    state = initialize_conversation_state()
    state["question"] = "What is X?"
    state["rag_context"] = [{"content": "X is Y."}]

    with patch('app.agents.executor.get_llm') as mock_get_llm, \
            patch('app.agents.executor._decide_web_search', return_value=(False, "")):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "根据资料，X 大概率与 Y 相关。你最近还有别的症状吗？"
        mock_get_llm.return_value = mock_llm

        new_state = ExecutorAgent(state)

        assert "大概率与 y 相关" in new_state["generation"].lower()
        assert len(new_state["conversation_history"]) == 2  # user + assistant


def test_executor_agent_no_llm():
    state = initialize_conversation_state()
    state["question"] = "test"
    with patch('app.agents.executor.get_llm', return_value=None):
        new_state = ExecutorAgent(state)
        assert "暂时不可用" in new_state["generation"]
        assert "你希望我下一步" in new_state["generation"]


def test_executor_agent_llm_fail():
    state = initialize_conversation_state()
    state["question"] = "test"
    state["documents"] = [Document(page_content="some content")]
    with patch('app.agents.executor.get_llm') as mock_get:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("error")
        mock_get.return_value = mock_llm
        new_state = ExecutorAgent(state)
        assert "咨询线下医生" in new_state["generation"]
        assert "你希望我下一步" in new_state["generation"]


def test_executor_ecg_skill_shortcut():
    state = initialize_conversation_state()
    state["session_id"] = "session-ecg-1"
    state["question"] = (
        "请根据以下ECG数据生成报告：```json"
        "{\"patient_info\":{\"age\":24,\"gender\":\"female\"},"
        "\"features\":{\"heart_rate\":74}}```"
    )
    with patch("app.agents.executor._maybe_run_ecg_skill") as mock_skill:
        mock_skill.return_value = MagicMock(
            report="**心电图诊断报告**\\n\\n**建议**\\n1. 复查",
            risk_level="low",
            disclaimer="仅供参考",
        )
        new_state = ExecutorAgent(state)
        mock_skill.assert_called_once_with(state["question"], "session-ecg-1")
        assert "心电图诊断报告" in new_state["generation"]
        assert new_state["source"] == "ECG Report Skill"
