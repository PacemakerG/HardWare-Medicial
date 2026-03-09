"""
MediGenius — agents/executor.py
ExecutorAgent: single sink node for final response synthesis.
It may call tools internally under strict stop conditions.
"""

import json
import re

from app.core.logging_config import logger
from app.core.state import AgentState
from app.schemas.ecg import ECGReportRequest
from app.services.ecg_report_service import ecg_report_service
from app.tools.llm_client import get_light_llm, get_llm
from app.tools.tavily_search import get_tavily_search

MAX_TOOL_CALLS = 2
MAX_SAME_TOOL_REPEAT = 1
DEFAULT_FOLLOW_UP_TEMPLATE = (
    "你希望我下一步重点帮你看哪一部分：症状变化、可能原因、用药建议，还是是否需要线下就医？"
)
HIGH_RISK_TEMPLATE = (
    "如果你现在出现胸痛持续加重、呼吸明显困难、意识模糊或晕厥，请立即前往急诊或呼叫急救。"
)
HIGH_RISK_KEYWORDS = (
    "胸痛",
    "呼吸困难",
    "意识模糊",
    "晕厥",
    "抽搐",
    "大出血",
    "严重过敏",
    "剧烈头痛",
    "持续高烧",
)

STYLE_ALIAS_MAP = {
    "warm": {"warm", "friendly", "gentle", "empathetic", "温和", "共情", "亲切"},
    "concise": {"concise", "brief", "direct", "简洁", "简短", "直接"},
    "professional": {"professional", "严谨", "专业", "正式"},
    "reassuring": {"reassuring", "supportive", "安抚", "鼓励"},
}
DETAIL_ALIAS_MAP = {
    "brief": {"brief", "concise", "short", "简洁", "简短"},
    "balanced": {"balanced", "normal", "standard", "适中", "标准"},
    "detailed": {"detailed", "deep", "full", "详细", "深入"},
}


def _recent_history_text(state: AgentState) -> str:
    lines = []
    for item in state.get("conversation_history", [])[-5:]:
        role = "Patient" if item.get("role") == "user" else "Doctor"
        lines.append(f"{role}: {item.get('content', '')}")
    return "\n".join(lines)


def _rag_context_text(state: AgentState) -> str:
    rag_context = state.get("rag_context") or []
    if not rag_context:
        return "No retrieved context."
    chunks = []
    for i, chunk in enumerate(rag_context[:5], start=1):
        chunks.append(f"[RAG-{i}] {chunk.get('content', '')}")
    return "\n\n".join(chunks)


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def _extract_embedded_json(text: str) -> dict | None:
    """Extract JSON object from markdown fenced block or raw text."""
    if not text:
        return None

    fenced = re.findall(r"```json\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    candidates = fenced or [text]
    for candidate in candidates:
        json_text = _extract_json_block(candidate)
        try:
            obj = json.loads(json_text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return None


def _maybe_run_ecg_skill(
    question: str,
    session_id: str = "",
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
):
    """
    If question contains ECG JSON payload, run ECG report skill directly.
    Expected payload keys include at least patient_info and features.
    """
    q = question.lower()
    if "ecg" not in q and "心电" not in q:
        return None

    payload = _extract_embedded_json(question)
    if not payload:
        return None
    if "patient_info" not in payload or "features" not in payload:
        return None

    try:
        request = ECGReportRequest.model_validate(payload)
        return ecg_report_service.generate_report(
            request,
            session_id=session_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except Exception as exc:
        logger.warning("ECG skill payload validation failed: %s", exc)
        return None


def _contains_question_sentence(text: str) -> bool:
    if "？" in text or "?" in text:
        return True
    inquiry_patterns = (
        "你可以告诉我",
        "你愿意告诉我",
        "是否方便说说",
        "想进一步了解",
        "下一步",
    )
    return any(p in text for p in inquiry_patterns)


def _is_mostly_chinese(text: str) -> bool:
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    latin = re.findall(r"[A-Za-z]", text)
    if not chinese:
        return False
    # Allow technical terms; require Chinese presence to dominate.
    return len(chinese) >= max(20, len(latin))


def _needs_high_risk_alert(question: str) -> bool:
    q = question.strip()
    return any(k in q for k in HIGH_RISK_KEYWORDS)


def _clean_preference_text(value, max_len: int = 40) -> str:
    if value is None:
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text:
        return ""
    return text[:max_len]


def _normalize_alias(raw: str, alias_map: dict[str, set[str]], default: str) -> str:
    if not raw:
        return default
    lowered = raw.lower()
    for normalized, aliases in alias_map.items():
        if lowered in aliases:
            return normalized
    return default


def _extract_personalization_preferences(state: AgentState) -> dict[str, str]:
    raw_prefs = state.get("user_preferences") or {}
    if not isinstance(raw_prefs, dict):
        raw_prefs = {}

    preferred_name = _clean_preference_text(
        raw_prefs.get("preferred_name")
        or raw_prefs.get("addressing_name")
        or raw_prefs.get("nickname")
    )
    communication_style = _normalize_alias(
        _clean_preference_text(raw_prefs.get("communication_style"), max_len=30),
        STYLE_ALIAS_MAP,
        "warm",
    )
    detail_level = _normalize_alias(
        _clean_preference_text(raw_prefs.get("detail_level"), max_len=20),
        DETAIL_ALIAS_MAP,
        "balanced",
    )
    language = _clean_preference_text(raw_prefs.get("language"), max_len=20)

    return {
        "preferred_name": preferred_name,
        "communication_style": communication_style,
        "detail_level": detail_level,
        "language": language,
    }


def _build_personalization_guidance(preferences: dict[str, str]) -> str:
    guidance_lines = []
    preferred_name = preferences.get("preferred_name", "")
    if preferred_name:
        guidance_lines.append(f"- 偏好称呼：优先称呼用户为“{preferred_name}”。")

    communication_style = preferences.get("communication_style", "warm")
    style_guidance = {
        "warm": "- 表达风格：保持温和、共情，但先给结论再关怀。",
        "concise": "- 表达风格：措辞直接、句子简短，减少冗余铺垫。",
        "professional": "- 表达风格：更偏专业与严谨，减少口语化表达。",
        "reassuring": "- 表达风格：先稳定情绪，再给明确可执行建议。",
    }
    guidance_lines.append(style_guidance.get(communication_style, style_guidance["warm"]))

    detail_level = preferences.get("detail_level", "balanced")
    detail_guidance = {
        "brief": "- 详略偏好：以关键结论和行动建议为主，内容简洁。",
        "balanced": "- 详略偏好：保持中等详细度，结论与解释平衡。",
        "detailed": "- 详略偏好：适度展开机制解释、观察点和就医阈值。",
    }
    guidance_lines.append(detail_guidance.get(detail_level, detail_guidance["balanced"]))

    language = preferences.get("language", "").lower()
    if language and language not in {"zh", "zh-cn", "chinese", "中文", "简体中文"}:
        guidance_lines.append(
            "- 语言偏好：主体仍用简体中文，必要时可补充少量偏好语言术语说明。"
        )

    if not guidance_lines:
        return "- 无显式偏好，使用默认温和专业风格。"
    return "\n".join(guidance_lines)


def _follow_up_template(preferred_name: str = "") -> str:
    if preferred_name:
        return f"{preferred_name}，{DEFAULT_FOLLOW_UP_TEMPLATE}"
    return DEFAULT_FOLLOW_UP_TEMPLATE


def _normalize_answer(answer: str, question: str, preferred_name: str = "") -> str:
    """Post-process answer for Chinese output, safety reminders, and proactive follow-up."""
    text = (answer or "").strip()
    if not text:
        text = "我理解你的担心，我先给你一个简要判断和下一步建议。"

    if not _is_mostly_chinese(text):
        # Lightweight deterministic fallback if model drifts to English.
        text = (
            "我先用中文给你简要说明：根据你目前提供的信息，建议先进行基础观察并避免自行加大用药。"
            "如果症状持续或加重，请尽快线下就医。"
        )

    if _needs_high_risk_alert(question) and HIGH_RISK_TEMPLATE not in text:
        text = f"{text}\n\n{HIGH_RISK_TEMPLATE}"

    if not _contains_question_sentence(text):
        text = f"{text}\n\n{_follow_up_template(preferred_name)}"

    return text


def _decide_web_search(state: AgentState) -> tuple[bool, str]:
    """
    Decide whether to trigger web search.
    Returns: (need_search, search_query)
    """
    question = state.get("question", "")
    rag_text = _rag_context_text(state)

    # Hard stop: tool budget exhausted.
    if state.get("tool_budget_used", 0) >= MAX_TOOL_CALLS:
        return False, ""

    light_llm = get_light_llm(
        tenant_id=state.get("tenant_id", "default"),
        user_id=state.get("user_id", "anonymous"),
    )
    if not light_llm:
        # Heuristic fallback for temporally-sensitive questions.
        temporal_hints = ("latest", "today", "recent", "new", "guideline", "news")
        if any(h in question.lower() for h in temporal_hints):
            return True, question
        return False, ""

    prompt = (
        "You are a tool routing assistant.\n"
        "Decide if web search is required to answer the user question accurately.\n"
        "Return ONLY JSON: {\"need_web_search\": true|false, \"search_query\": \"...\"}\n\n"
        f"Question: {question[:1200]}\n"
        f"Retrieved context summary:\n{rag_text[:2400]}\n"
    )
    try:
        raw = light_llm.invoke(prompt)
        content = raw.content if hasattr(raw, "content") else str(raw)
        parsed = json.loads(_extract_json_block(content))
        need_search = bool(parsed.get("need_web_search", False))
        search_query = (parsed.get("search_query") or question).strip()
        return need_search, search_query
    except Exception as exc:
        logger.warning("Executor tool decision failed: %s", exc)
        return False, ""


def _run_web_search(state: AgentState, query: str) -> str:
    """Run Tavily web search once and return compact evidence text."""
    tool_calls = state.get("tool_calls", [])
    same_tool_uses = [c for c in tool_calls if c.get("tool") == "web_search"]
    if len(same_tool_uses) >= MAX_SAME_TOOL_REPEAT:
        logger.info("Executor: web search skipped due to repeat limit")
        return ""

    tavily = get_tavily_search()
    if not tavily:
        logger.info("Executor: web search unavailable (no Tavily key)")
        return ""

    try:
        results = tavily.invoke(query)
    except Exception as exc:
        logger.error("Executor web search failed: %s", exc)
        return ""

    valid = [
        item
        for item in (results or [])
        if isinstance(item, dict) and (item.get("content") or "").strip()
    ][:3]
    if not valid:
        return ""

    state["tool_calls"].append({"tool": "web_search", "query": query})
    state["tool_budget_used"] = state.get("tool_budget_used", 0) + 1
    state["source"] = "Current Medical Research & News"

    snippets = []
    for idx, item in enumerate(valid, start=1):
        title = item.get("title", "Untitled")
        content = item.get("content", "")[:700]
        snippets.append(f"[WEB-{idx}] {title}\n{content}")
    return "\n\n".join(snippets)


def ExecutorAgent(state: AgentState) -> AgentState:
    """Generate final answer with optional internal web-search tool usage."""
    llm = get_llm(
        tenant_id=state.get("tenant_id", "default"),
        user_id=state.get("user_id", "anonymous"),
    )
    question = state["question"]
    source_info = state.get("source", "AI Medical Knowledge")
    memory_context = state.get("memory_context") or "No persistent memory context."
    user_preferences = _extract_personalization_preferences(state)
    personalization_guidance = _build_personalization_guidance(user_preferences)
    preferred_name = user_preferences.get("preferred_name", "")
    rag_text = _rag_context_text(state)
    history_text = _recent_history_text(state)
    web_evidence = ""

    # Decide web-search usage under strict stop conditions.
    need_web_search, search_query = _decide_web_search(state)
    if need_web_search and search_query:
        web_evidence = _run_web_search(state, search_query)
        if web_evidence:
            source_info = "Current Medical Research & News"
        else:
            source_info = (
                "Medical Literature Database"
                if state.get("rag_context")
                else "AI Medical Knowledge"
            )
    else:
        source_info = (
            "Medical Literature Database"
            if state.get("rag_context")
            else "AI Medical Knowledge"
        )

    # Skill shortcut: if user embeds ECG payload, generate ECG report directly.
    ecg_skill_output = _maybe_run_ecg_skill(
        question,
        state.get("session_id", ""),
        tenant_id=state.get("tenant_id", "default"),
        user_id=state.get("user_id", "anonymous"),
    )
    if ecg_skill_output is not None:
        answer = (
            f"{ecg_skill_output.report}\n\n"
            f"风险等级：{ecg_skill_output.risk_level}\n"
            f"免责声明：{ecg_skill_output.disclaimer}"
        )
        answer = _normalize_answer(answer, question, preferred_name=preferred_name)
        source_info = "ECG Report Skill"
        state["generation"] = answer
        state["source"] = source_info
        state["conversation_history"].append({"role": "user", "content": question})
        state["conversation_history"].append(
            {"role": "assistant", "content": answer, "source": source_info}
        )
        logger.info("Executor: ECG report skill executed")
        return state

    if not llm:
        answer = (
            "当前医疗助手服务暂时不可用，建议你先进行基础观察，必要时尽快咨询线下医生。"
        )
        source_info = "System Message"
    else:
        prompt = (
            "你是一位有温度、谨慎且专业的中文个人医疗助手。\n"
            "输出必须使用简体中文（必要的医学名词可保留英文缩写）。\n"
            "不要过度诊断；证据不足时明确说明不确定性。\n"
            "回答格式必须遵循：\n"
            "1) 先直接回应用户当前问题（1-2句）\n"
            "2) 再给出1-3条可执行的下一步建议\n"
            "3) 最后必须主动追问一个下一步问题，引导继续对话\n"
            "4) 若出现高风险症状，优先提示紧急就医阈值\n\n"
            "在不影响医学准确性的前提下，遵循以下个性化偏好：\n"
            f"{personalization_guidance}\n\n"
            f"用户长期画像:\n{memory_context}\n\n"
            f"最近对话:\n{history_text or '暂无历史对话'}\n\n"
            f"用户问题:\n{question}\n\n"
            f"RAG资料:\n{rag_text}\n\n"
            f"联网资料:\n{web_evidence or '暂无联网资料'}\n\n"
            "请给出清晰、可执行、有人情味的中文回答。"
        )
        try:
            response = llm.invoke(prompt)
            answer = (
                response.content.strip()
                if hasattr(response, "content")
                else str(response).strip()
            )
            answer = _normalize_answer(answer, question, preferred_name=preferred_name)
            state["llm_success"] = bool(answer)
            state["llm_attempted"] = True
            logger.info(
                "Executor: Final response generated (web_used=%s, rag_used=%s)",
                bool(web_evidence),
                bool(state.get("rag_context")),
            )
        except Exception as exc:
            logger.error("Executor: LLM generation failed: %s", exc)
            answer = (
                "我理解你的担心，目前我无法稳定生成可靠建议。请优先咨询线下医生进行明确评估。"
            )
            answer = _normalize_answer(answer, question, preferred_name=preferred_name)
            source_info = "System Message"
            state["llm_success"] = False
            state["llm_attempted"] = True

    if source_info == "System Message":
        answer = _normalize_answer(answer, question, preferred_name=preferred_name)

    state["generation"] = answer
    state["source"] = source_info
    state["conversation_history"].append({"role": "user", "content": question})
    state["conversation_history"].append(
        {"role": "assistant", "content": answer, "source": source_info}
    )
    return state
