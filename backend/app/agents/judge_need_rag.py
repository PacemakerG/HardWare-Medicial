"""
MediGenius — agents/judge_need_rag.py
JudgeNeedRAGAgent: lightweight classifier deciding whether retrieval is needed.
"""

import json

from app.core.logging_config import logger
from app.core.state import AgentState
from app.tools.llm_client import get_light_llm


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def JudgeNeedRAGAgent(state: AgentState) -> AgentState:
    """
    Decide whether query needs retrieval.
    Strict output target:
      {"need_rag": true|false, "reason": "..."}
    """
    question = (state.get("question") or "").strip()
    if not question:
        state["need_rag"] = False
        return state

    # Fast-path heuristic for simple greetings/chitchat.
    lightweight_chitchat = {"hi", "hello", "hey", "thanks", "thank you"}
    if question.lower() in lightweight_chitchat:
        state["need_rag"] = False
        state["search_query"] = None
        return state

    llm = get_light_llm()
    if not llm:
        # Conservative fallback: for non-keyword route, avoid retrieval by default.
        state["need_rag"] = False
        return state

    prompt = (
        "You are a strict router for a medical assistant workflow.\n"
        "Decide whether retrieval from medical documents is required.\n"
        "Return ONLY JSON: {\"need_rag\": true|false, \"reason\": \"...\"}\n\n"
        f"User question: {question[:1200]}\n"
    )

    try:
        raw = llm.invoke(prompt)
        content = raw.content if hasattr(raw, "content") else str(raw)
        parsed = json.loads(_extract_json_block(content))
        need_rag = bool(parsed.get("need_rag", False))
        state["need_rag"] = need_rag
        state["search_query"] = question if need_rag else None
        logger.info("JudgeNeedRAG: need_rag=%s", need_rag)
    except Exception as exc:
        logger.warning("JudgeNeedRAG failed, fallback to no-rag: %s", exc)
        state["need_rag"] = False
        state["search_query"] = None

    return state
