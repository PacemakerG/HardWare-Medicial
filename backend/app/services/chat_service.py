"""
MediGenius — services/chat_service.py
ChatService: orchestrates the LangGraph agentic workflow for each chat message.
"""

from datetime import datetime
from typing import Any, AsyncGenerator, Dict
import threading

from app.agents.executor import (
    build_executor_plan,
    finalize_executor_state,
    normalize_executor_answer,
)
from app.agents.judge_need_rag import JudgeNeedRAGAgent
from app.agents.memory import MemoryReadAgent, MemoryWriteAsyncAgent
from app.agents.medical_router import MedicalRouterAgent
from app.agents.planner import KeywordRouterAgent
from app.agents.query_rewriter import QueryRewriterAgent
from app.agents.retriever import RetrieverAgent
from app.agents.reranker import RerankerAgent
from app.core.langgraph_workflow import create_workflow
from app.core.logging_config import logger
from app.core.state import initialize_conversation_state, reset_query_state
from app.services.database_service import db_service
from app.services.flow_trace_service import append_flow_trace_record
from app.tools.llm_client import get_llm


class ChatService:
    """Orchestrates the agentic workflow for each chat message."""

    def __init__(self):
        self.workflow_app = None
        self.conversation_states: Dict[str, Dict] = {}
        self._lock = threading.Lock()
        logger.info("ChatService initialized")

    @staticmethod
    def _context_key(tenant_id: str, user_id: str, session_id: str) -> str:
        return f"{tenant_id}::{user_id}::{session_id}"

    def initialize_workflow(self) -> None:
        """Compile and cache the LangGraph workflow (called once at startup)."""
        if not self.workflow_app:
            logger.info("Initializing LangGraph workflow...")
            self.workflow_app = create_workflow()
            logger.info("LangGraph workflow initialized successfully")

    @staticmethod
    def _legacy_context_key(tenant_id: str, user_id: str, session_id: str) -> str | None:
        if tenant_id == "default" and user_id == "anonymous":
            return session_id
        return None

    def _load_persisted_history(
        self,
        session_id: str,
        *,
        tenant_id: str,
        user_id: str,
    ) -> list[dict]:
        """Bootstrap in-memory conversation history from persisted chat records."""
        history = db_service.get_chat_history(
            session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        restored = []
        for item in history[-20:]:
            record = {
                "role": item.get("role", ""),
                "content": item.get("content", ""),
            }
            if item.get("source"):
                record["source"] = item["source"]
            restored.append(record)
        return restored

    def _prepare_query_state(
        self,
        *,
        session_id: str,
        message: str,
        tenant_id: str,
        user_id: str,
    ) -> tuple[str, Dict[str, Any]]:
        context_key = self._context_key(tenant_id, user_id, session_id)
        legacy_key = self._legacy_context_key(tenant_id, user_id, session_id)
        with self._lock:
            if context_key not in self.conversation_states:
                state = initialize_conversation_state()
                state["conversation_history"] = self._load_persisted_history(
                    session_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
                self.conversation_states[context_key] = state
                if legacy_key:
                    self.conversation_states[legacy_key] = state
            state = self.conversation_states[context_key]
        state = reset_query_state(state)
        state["tenant_id"] = tenant_id
        state["user_id"] = user_id
        state["session_id"] = session_id
        state["question"] = message
        return context_key, state

    def _store_state(self, context_key: str, result: Dict[str, Any]) -> None:
        with self._lock:
            if context_key not in self.conversation_states:
                self.conversation_states[context_key] = initialize_conversation_state()
            self.conversation_states[context_key].update(result)
            tenant_id, user_id, session_id = context_key.split("::", 2)
            legacy_key = self._legacy_context_key(tenant_id, user_id, session_id)
            if legacy_key:
                self.conversation_states[legacy_key] = self.conversation_states[context_key]

    @staticmethod
    def _extract_chunk_text(chunk: Any) -> str:
        if chunk is None:
            return ""

        content = chunk.content if hasattr(chunk, "content") else chunk
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue
                if isinstance(item, dict):
                    text = item.get("text") or item.get("content")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)
        return ""

    async def process_message(
        self,
        session_id: str,
        message: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> Dict[str, Any]:
        """Run the agentic pipeline for a single user message."""
        logger.info(
            "Processing message tenant=%s user=%s session=%s...",
            tenant_id,
            user_id,
            session_id[:8],
        )

        if not self.workflow_app:
            raise ValueError("Workflow not initialized")

        # Persist user message
        db_service.save_message(
            session_id,
            "user",
            message,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        context_key, state = self._prepare_query_state(
            session_id=session_id,
            message=message,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Run workflow (async preferred, sync fallback)
        try:
            result = await self.workflow_app.ainvoke(state)
        except AttributeError:
            logger.warning("Falling back to sync invoke")
            result = self.workflow_app.invoke(state)

        self._store_state(context_key, result)

        response_text = result.get("generation", "Unable to generate response.")
        source = result.get("source", "Unknown")
        flow_trace = result.get("flow_trace", [])

        # Persist assistant response
        db_service.save_message(
            session_id,
            "assistant",
            response_text,
            source,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        append_flow_trace_record(
            session_id=session_id,
            question=message,
            flow_trace=flow_trace,
            source=source,
            safety_level=result.get("safety_level", "SAFE"),
            domain=result.get("domain", "general"),
            primary_department=result.get("primary_department", "") or "",
            use_rag=bool(result.get("use_rag", False)),
            need_rag=bool(result.get("need_rag", False)),
        )

        return {
            "response": response_text,
            "source": source,
            "timestamp": datetime.now().strftime("%I:%M %p"),
            "success": bool(result.get("generation")),
            "flow_trace": flow_trace,
        }

    async def process_message_stream(
        self,
        session_id: str,
        message: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Run shared pre-processing and stream LLM tokens as they are generated."""
        logger.info(
            "Streaming message tenant=%s user=%s session=%s...",
            tenant_id,
            user_id,
            session_id[:8],
        )
        if not self.workflow_app:
            raise ValueError("Workflow not initialized")

        db_service.save_message(
            session_id,
            "user",
            message,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        context_key, state = self._prepare_query_state(
            session_id=session_id,
            message=message,
            tenant_id=tenant_id,
            user_id=user_id,
        )

        # Mirror workflow up to executor so stream path is behaviorally aligned.
        state = MemoryReadAgent(state)
        state = KeywordRouterAgent(state)

        if state.get("safety_level") in {"EMERGENCY", "CLARIFY"}:
            pass
        elif state.get("domain") == "medical":
            if state.get("use_rag"):
                state = MedicalRouterAgent(state)
                state = QueryRewriterAgent(state)
                state = RetrieverAgent(state)
                state = RerankerAgent(state)
            else:
                state = JudgeNeedRAGAgent(state)
                if state.get("need_rag"):
                    state = QueryRewriterAgent(state)
                    state = RetrieverAgent(state)
                    state = RerankerAgent(state)
        elif state.get("use_rag"):
            state = QueryRewriterAgent(state)
            state = RetrieverAgent(state)
            state = RerankerAgent(state)
        else:
            state = JudgeNeedRAGAgent(state)
            if state.get("need_rag"):
                state = QueryRewriterAgent(state)
                state = RetrieverAgent(state)
                state = RerankerAgent(state)

        plan = build_executor_plan(state)
        question = plan.get("question", message)
        preferred_name = plan.get("preferred_name", "")
        source_info = plan.get("source_info", state.get("source", "Unknown"))
        streamed_text = ""
        emitted_fallback_delta = False

        if plan.get("mode") == "shortcut":
            answer = plan.get("answer", "")
            if answer:
                yield {"event": "delta", "delta": answer}
        else:
            llm = get_llm(tenant_id=tenant_id, user_id=user_id)
            if not llm:
                answer = normalize_executor_answer(
                    "当前医疗助手服务暂时不可用，建议你先进行基础观察，必要时尽快咨询线下医生。",
                    question,
                    preferred_name=preferred_name,
                )
                source_info = "System Message"
                yield {"event": "delta", "delta": answer}
                emitted_fallback_delta = True
            else:
                try:
                    prompt = plan.get("prompt", "")
                    async for chunk in llm.astream(prompt):
                        delta = self._extract_chunk_text(chunk)
                        if not delta:
                            continue
                        streamed_text += delta
                        yield {"event": "delta", "delta": delta}
                    answer = normalize_executor_answer(
                        streamed_text,
                        question,
                        preferred_name=preferred_name,
                    )
                    state["llm_success"] = bool(answer)
                    state["llm_attempted"] = True
                except Exception as exc:
                    logger.error("Streaming LLM generation failed: %s", exc)
                    if streamed_text.strip():
                        answer = normalize_executor_answer(
                            streamed_text,
                            question,
                            preferred_name=preferred_name,
                        )
                    else:
                        answer = normalize_executor_answer(
                            "我理解你的担心，目前我无法稳定生成可靠建议。请优先咨询线下医生进行明确评估。",
                            question,
                            preferred_name=preferred_name,
                        )
                        source_info = "System Message"
                        yield {"event": "delta", "delta": answer}
                        emitted_fallback_delta = True
                    state["llm_success"] = False
                    state["llm_attempted"] = True

        # Keep the final output aligned with post-processing rules.
        if streamed_text and answer.startswith(streamed_text):
            suffix = answer[len(streamed_text) :]
            if suffix:
                yield {"event": "delta", "delta": suffix}
        elif (not streamed_text) and answer and (not emitted_fallback_delta):
            yield {"event": "delta", "delta": answer}

        state = finalize_executor_state(state, answer=answer, source_info=source_info)
        state = MemoryWriteAsyncAgent(state)
        self._store_state(context_key, state)
        flow_trace = state.get("flow_trace", [])

        db_service.save_message(
            session_id,
            "assistant",
            answer,
            source_info,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        append_flow_trace_record(
            session_id=session_id,
            question=message,
            flow_trace=flow_trace,
            source=source_info,
            safety_level=state.get("safety_level", "SAFE"),
            domain=state.get("domain", "general"),
            primary_department=state.get("primary_department", "") or "",
            use_rag=bool(state.get("use_rag", False)),
            need_rag=bool(state.get("need_rag", False)),
        )
        yield {
            "event": "done",
            "success": bool(answer),
            "response": answer,
            "source": source_info,
            "timestamp": datetime.now().strftime("%I:%M %p"),
            "flow_trace": flow_trace,
        }

    def clear_conversation(
        self,
        session_id: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> None:
        """Reset the in-memory conversation state for a session."""
        context_key = self._context_key(tenant_id, user_id, session_id)
        legacy_key = self._legacy_context_key(tenant_id, user_id, session_id)
        with self._lock:
            if context_key in self.conversation_states:
                reset_state = initialize_conversation_state()
                self.conversation_states[context_key] = reset_state
                if legacy_key:
                    self.conversation_states[legacy_key] = reset_state
                logger.info(
                    "Conversation cleared tenant=%s user=%s session=%s",
                    tenant_id,
                    user_id,
                    session_id[:8],
                )


# Module-level singleton
chat_service = ChatService()
