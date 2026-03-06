import os
import sys
from unittest.mock import MagicMock, patch

from fastapi import Request
from langchain_core.documents import Document

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.agents.executor import ExecutorAgent  # noqa: E402
from app.api.v1.endpoints.chat import _get_session_id  # noqa: E402
from app.api.v1.endpoints.session import (  # noqa: E402
    delete_session_endpoint,
    get_sessions_endpoint,
)
from app.core.state import initialize_conversation_state  # noqa: E402
from app.main import lifespan  # noqa: E402
from app.tools.vector_store import get_or_create_vectorstore  # noqa: E402


def test_executor_full_coverage():
    # Branch 1: if not llm
    state = initialize_conversation_state()
    with patch("app.agents.executor.get_llm", return_value=None), \
            patch("app.agents.executor._decide_web_search", return_value=(False, "")):
        res = ExecutorAgent(state)
        assert "暂时不可用" in res["generation"]

    # Branch 2: documents branch (hits history context)
    state = initialize_conversation_state()
    state["rag_context"] = [{"content": "info"}]
    state["conversation_history"] = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"}
    ]
    with patch("app.agents.executor.get_llm") as mock_get, \
            patch("app.agents.executor._decide_web_search", return_value=(False, "")):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value.content = "基于资料判断，建议先观察 24 小时。你是否还有发热？"
        mock_get.return_value = mock_llm
        res = ExecutorAgent(state)
        assert "建议先观察" in res["generation"]
        assert len(res["conversation_history"]) >= 2

    # Branch 3: no rag/no web path with llm available
    state = initialize_conversation_state()
    state["question"] = "general question"
    with patch("app.agents.executor.get_llm") as mock_get, \
            patch("app.agents.executor._decide_web_search", return_value=(False, "")):
        mock_get.return_value = MagicMock()
        mock_get.return_value.invoke.return_value.content = "可以先从作息和补水开始调整。你这两天睡眠怎么样？"
        res = ExecutorAgent(state)
        assert "作息和补水" in res["generation"]

    # Branch 4: llm exception fallback
    state = initialize_conversation_state()
    with patch("app.agents.executor.get_llm") as mock_get, \
            patch("app.agents.executor._decide_web_search", return_value=(False, "")):
        mock_get.return_value = MagicMock()
        mock_get.return_value.invoke.side_effect = Exception("boom")
        res = ExecutorAgent(state)
        assert "咨询线下医生" in res["generation"]


def test_executor_web_search_branch():
    state = initialize_conversation_state()
    state["question"] = "latest guideline"
    with patch("app.agents.executor.get_llm") as mock_get, \
            patch("app.agents.executor._decide_web_search", return_value=(True, "query")), \
            patch("app.agents.executor._run_web_search", return_value="web evidence"):
        mock_get.return_value = MagicMock()
        mock_get.return_value.invoke.return_value.content = "结合最新资料，先进行居家监测。你目前体温大概多少？"
        res = ExecutorAgent(state)
        assert "结合最新资料" in res["generation"]


def test_executor_auto_append_followup():
    state = initialize_conversation_state()
    state["question"] = "我最近头痛"
    with patch("app.agents.executor.get_llm") as mock_get, \
            patch("app.agents.executor._decide_web_search", return_value=(False, "")):
        mock_get.return_value = MagicMock()
        mock_get.return_value.invoke.return_value.content = "建议先保证休息并补充水分。"
        res = ExecutorAgent(state)
        assert "你希望我下一步" in res["generation"]


def test_get_session_id_no_header():
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.session = {}
    sid = _get_session_id(mock_request)
    assert sid is not None
    assert mock_request.session["session_id"] == sid


def test_session_endpoints_coverage():
    from app.api.v1.endpoints.session import _get_session_id as _get_sid_s
    mock_request = MagicMock(spec=Request)
    mock_request.headers = {}
    mock_request.session = {}
    sid = _get_sid_s(mock_request)
    assert sid is not None

    with patch("app.api.v1.endpoints.session.db_service") as mock_db:
        mock_db.get_all_sessions.return_value = []
        import asyncio
        res = asyncio.run(get_sessions_endpoint())
        assert res["sessions"] == []

        mock_db.delete_session.return_value = True
        mock_request.session = {"session_id": sid}
        res_del = asyncio.run(delete_session_endpoint(sid, mock_request))
        assert res_del["success"] is True


def test_lifespan_no_pdf():
    app = MagicMock()
    # Mocking PDF paths
    pdf_paths = ["medical_book.pdf", "database/medical_book.pdf"]
    with patch("os.path.exists", side_effect=lambda p: False if any(x in p for x in pdf_paths) else True):
        with patch("app.main.db_service"):
            with patch("app.main.chat_service"):
                import asyncio
                gen = lifespan(app)

                async def run_startup():
                    async with gen:
                        pass
                asyncio.run(run_startup())


def test_vector_store_coverage():
    with patch("app.tools.vector_store.get_embeddings", return_value=MagicMock()):
        from app.tools import vector_store
        vector_store._vectorstore = None
        with patch("langchain_community.vectorstores.Chroma") as mock_chroma:
            mock_vs = MagicMock()
            mock_vs._collection.count.return_value = 0
            mock_chroma.return_value = mock_vs
            with patch("os.path.exists", return_value=True):
                with patch("os.listdir", return_value=["chroma.sqlite3"]):
                    res = get_or_create_vectorstore(persist_dir="fake_dir_empty")
                    assert res is None

        vector_store._vectorstore = None
        with patch("os.path.exists", return_value=False):
            with patch("os.makedirs"):
                    res = get_or_create_vectorstore(documents=None, persist_dir="new_fake_dir")
                    assert res is None


def test_vector_store_no_embeddings():
    from app.tools import vector_store
    vector_store._vectorstore = None
    with patch("app.tools.vector_store.get_embeddings", return_value=None):
        assert get_or_create_vectorstore(persist_dir="fake_dir") is None


def test_db_session_makedirs():
    from app.db.session import get_engine
    with patch("os.path.exists", return_value=False):
        with patch("os.makedirs") as mock_makedirs:
            get_engine("some_new_dir/db.sqlite3")
            mock_makedirs.assert_called()


def test_main_uvicorn():
    # Conceptually hit main entry point
    with patch("uvicorn.run"):
        pass
