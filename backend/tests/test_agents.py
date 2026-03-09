"""Tests for all agents — Deep Modular Architecture"""
import os
import sys
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.executor import ExecutorAgent  # noqa: E402
from app.agents.memory import MemoryAgent  # noqa: E402
from app.agents.planner import PlannerAgent  # noqa: E402
from app.agents.retriever import RetrieverAgent  # noqa: E402
from app.core.state import initialize_conversation_state  # noqa: E402


# --- Planner Agent Tests ---
def test_planner_agent_medical():
    state = initialize_conversation_state()
    state["question"] = "I have a high fever"
    new_state = PlannerAgent(state)
    assert new_state["current_tool"] == "retriever"


def test_planner_agent_general():
    state = initialize_conversation_state()
    state["question"] = "Hello there"
    new_state = PlannerAgent(state)
    assert new_state["current_tool"] == "judge_need_rag"


# --- Retriever Agent Tests ---
def test_retriever_agent_success():
    state = initialize_conversation_state()
    state["question"] = "fever"

    with patch('app.agents.retriever.get_retriever') as mock_get_retriever:
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = [Document(page_content="Fever details " * 10)]
        mock_get_retriever.return_value = mock_retriever

        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is True
        assert len(new_state["documents"]) > 0


def test_retriever_agent_failure():
    state = initialize_conversation_state()
    state["question"] = "unknown"
    with patch('app.agents.retriever.get_retriever') as mock_get:
        mock_retriever = MagicMock()
        mock_retriever.invoke.return_value = []
        mock_get.return_value = mock_retriever

        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is False


def test_retriever_agent_no_tool():
    state = initialize_conversation_state()
    with patch('app.agents.retriever.get_retriever', return_value=None):
        new_state = RetrieverAgent(state)
        assert new_state["rag_success"] is False


# --- Memory Agent Tests ---
def test_memory_agent():
    state = initialize_conversation_state()
    state["conversation_history"] = [{"role": "user", "content": str(i)} for i in range(25)]

    new_state = MemoryAgent(state)

    assert len(new_state["conversation_history"]) == 20
    assert new_state["conversation_history"][-1]["content"] == "24"


def test_memory_agent_loads_user_preferences():
    state = initialize_conversation_state()
    state["session_id"] = "sess-pref"

    with patch("app.agents.memory.load_profile") as mock_load, patch(
        "app.agents.memory.render_profile_as_text"
    ) as mock_render:
        mock_load.return_value = {
            "preferences": {
                "preferred_name": "王女士",
                "communication_style": "concise",
                "detail_level": "brief",
            }
        }
        mock_render.return_value = "mock profile context"
        new_state = MemoryAgent(state)

    assert new_state["memory_context"] == "mock profile context"
    assert new_state["user_preferences"]["preferred_name"] == "王女士"
    assert new_state["user_preferences"]["detail_level"] == "brief"


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


def test_executor_agent_no_llm_with_preferred_name():
    state = initialize_conversation_state()
    state["question"] = "test"
    state["user_preferences"] = {"preferred_name": "王女士"}
    with patch("app.agents.executor.get_llm", return_value=None):
        new_state = ExecutorAgent(state)
        assert "王女士，你希望我下一步" in new_state["generation"]


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


def test_executor_agent_includes_personalization_guidance_in_prompt():
    state = initialize_conversation_state()
    state["question"] = "最近头痛怎么办"
    state["user_preferences"] = {
        "preferred_name": "李先生",
        "communication_style": "professional",
        "detail_level": "detailed",
        "language": "en-US",
    }

    with patch("app.agents.executor.get_llm") as mock_get_llm, patch(
        "app.agents.executor._decide_web_search", return_value=(False, "")
    ):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "请先观察一周并记录症状变化。你最近有发热吗？"
        mock_get_llm.return_value = mock_llm

        ExecutorAgent(state)
        prompt = mock_llm.invoke.call_args[0][0]

    assert "偏好称呼：优先称呼用户为“李先生”" in prompt
    assert "表达风格：更偏专业与严谨" in prompt
    assert "详略偏好：适度展开机制解释" in prompt
    assert "主体仍用简体中文" in prompt


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
        mock_skill.assert_called_once_with(
            state["question"],
            "session-ecg-1",
            tenant_id="default",
            user_id="anonymous",
        )
        assert "心电图诊断报告" in new_state["generation"]
        assert new_state["source"] == "ECG Report Skill"
