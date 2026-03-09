"""
MediGenius — agents/judge_need_rag.py
JudgeNeedRAGAgent: lightweight classifier deciding whether retrieval is needed.
"""

import json

from app.core.logging_config import logger
from app.core.state import AgentState, append_flow_trace
from app.tools.llm_client import get_light_llm

LIGHTWEIGHT_CHITCHAT = {
    "hi",
    "hello",
    "hey",
    "thanks",
    "thank you",
    "你好",
    "您好",
    "哈喽",
    "嗨",
    "谢谢",
    "谢谢你",
}


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
    append_flow_trace(state, "judge_need_rag")
    question = (state.get("question") or "").strip()
    if not question:
        state["need_rag"] = False
        return state

    # Fast-path heuristic for simple greetings/chitchat.
    if question.lower() in LIGHTWEIGHT_CHITCHAT:
        state["need_rag"] = False
        state["search_query"] = None
        return state

    llm = get_light_llm()
    if not llm:
        # Conservative fallback: for non-keyword route, avoid retrieval by default.
        state["need_rag"] = False
        return state

    prompt = (
        "你是医疗助手工作流中的严格路由器。\n"
        "请判断当前问题是否需要从医疗文档中检索资料。\n"
        "只返回 JSON：{\"need_rag\": true|false, \"reason\": \"...\"}\n\n"
        f"用户问题：{question[:1200]}\n"
    )

    try:
        raw = llm.invoke(prompt)
        content = raw.content if hasattr(raw, "content") else str(raw)
        parsed = json.loads(_extract_json_block(content))
        need_rag = bool(parsed.get("need_rag", False))
        state["need_rag"] = need_rag
        state["search_query"] = question if need_rag else None
        state["current_tool"] = "query_rewriter" if need_rag else "executor"
        logger.info("JudgeNeedRAG: need_rag=%s", need_rag)
    except Exception as exc:
        logger.warning("JudgeNeedRAG failed, fallback to no-rag: %s", exc)
        state["need_rag"] = False
        state["search_query"] = None
        state["current_tool"] = "executor"

    return state
