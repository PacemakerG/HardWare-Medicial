"""
MediGenius — agents/executor.py
ExecutorAgent: single sink node for final response synthesis.
It may call tools internally under strict stop conditions.
"""

import json
import re

from app.core.logging_config import logger
from app.core.state import AgentState, append_flow_trace
from app.schemas.ecg import ECGReportRequest
from app.services.ecg_report_service import ecg_report_service
from app.tools.llm_client import get_light_llm, get_llm
from app.tools.tavily_search import get_tavily_search

MAX_TOOL_CALLS = 2
MAX_SAME_TOOL_REPEAT = 1
FOLLOW_UP_TEMPLATE = (
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


def _recent_history_text(state: AgentState) -> str:
    lines = []
    for item in state.get("conversation_history", [])[-5:]:
        role = "用户" if item.get("role") == "user" else "助手"
        lines.append(f"{role}: {item.get('content', '')}")
    return "\n".join(lines)


def _rag_context_text(state: AgentState) -> str:
    rag_context = state.get("rag_context") or []
    if not rag_context:
        return "暂无检索资料。"
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


def _maybe_run_ecg_skill(question: str, session_id: str = ""):
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
        return ecg_report_service.generate_report(request, session_id=session_id)
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


def _is_lightweight_chitchat(question: str) -> bool:
    return question.strip().lower() in LIGHTWEIGHT_CHITCHAT


def _finalize_response(
    state: AgentState,
    question: str,
    answer: str,
    source_info: str,
) -> AgentState:
    state["generation"] = answer
    state["source"] = source_info
    state["conversation_history"].append({"role": "user", "content": question})
    state["conversation_history"].append(
        {"role": "assistant", "content": answer, "source": source_info}
    )
    return state


def _normalize_answer(answer: str, question: str) -> str:
    """Post-process answer for Chinese output, safety reminders, and proactive follow-up."""
    text = (answer or "").strip()
    if not text:
        text = "我理解你的担心，我先给你一个简要判断和下一步建议。"

    if _is_lightweight_chitchat(question):
        if re.search(r"[\u4e00-\u9fff]", text):
            return text
        return "你好，我在。你想聊健康问题、饮食、运动、睡眠，还是心电数据？"

    if not _is_mostly_chinese(text):
        # Lightweight deterministic fallback if model drifts to English.
        text = (
            "我先用中文给你简要说明：根据你目前提供的信息，建议先进行基础观察并避免自行加大用药。"
            "如果症状持续或加重，请尽快线下就医。"
        )

    if _needs_high_risk_alert(question) and HIGH_RISK_TEMPLATE not in text:
        text = f"{text}\n\n{HIGH_RISK_TEMPLATE}"

    if not _contains_question_sentence(text):
        text = f"{text}\n\n{FOLLOW_UP_TEMPLATE}"

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

    light_llm = get_light_llm()
    if not light_llm:
        # Heuristic fallback for temporally-sensitive questions.
        temporal_hints = ("latest", "today", "recent", "new", "guideline", "news", "最新", "今天", "近期", "指南", "新闻")
        if any(h in question.lower() for h in temporal_hints):
            return True, question
        return False, ""

    prompt = (
        "你是工具路由助手。\n"
        "请判断为了准确回答用户问题，是否需要联网搜索。\n"
        "只返回 JSON：{\"need_web_search\": true|false, \"search_query\": \"...\"}\n\n"
        f"用户问题：{question[:1200]}\n"
        f"已检索资料摘要：\n{rag_text[:2400]}\n"
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
    append_flow_trace(state, "executor")
    llm = get_llm()
    question = state["question"]
    safety_level = state.get("safety_level", "SAFE")
    domain = state.get("domain", "general")
    primary_department = state.get("primary_department") or "未细分"
    source_info = state.get("source") or f"{domain.capitalize()} AI Coach"
    memory_context = state.get("memory_context") or "暂无长期记忆信息。"
    rag_text = _rag_context_text(state)
    history_text = _recent_history_text(state)
    ecg_info = state.get("ecg_metrics", "").strip() or "暂无最新数据"
    rag_source = state.get("source") if state.get("rag_context") else ""
    web_evidence = ""

    if safety_level == "EMERGENCY":
        answer = (
            "⚠️ 系统警报：检测到你描述的情况可能存在紧急医疗风险。"
            "我不能替代急救处置，请立即停止当前活动，尽快前往最近的急诊或立即拨打当地急救电话。"
        )
        logger.warning("Executor: emergency safety response triggered")
        return _finalize_response(state, question, answer, "Safety Guard")

    if safety_level == "CLARIFY":
        if not llm:
            answer = (
                "我需要先确认风险，再决定是否适合继续讨论。"
                "这个症状是你现在正在发生的吗？已经持续多久，是否在加重？"
            )
        else:
            prompt = (
                "你是一个负责任的健康管家。用户提到了敏感健康症状，但目前不能确定是否为急症。\n"
                "不要给出任何诊断、治疗、用药或处置建议。\n"
                "请只用关切、简洁的中文提出 1 到 2 个关键澄清问题，确认症状是否正在发生、持续多久、是否明显加重。\n\n"
                f"用户问题：{question}\n"
                f"历史对话：\n{history_text or '暂无历史对话'}\n"
            )
            try:
                result = llm.invoke(prompt)
                answer = result.content if hasattr(result, "content") else str(result)
            except Exception as exc:
                logger.warning("Executor: clarify prompt failed, using fallback: %s", exc)
                answer = (
                    "我先不急着给建议。这个症状是你现在正在发生的吗？"
                    "它大概持续了多久，程度是在加重还是已经缓解？"
                )
        return _finalize_response(state, question, answer.strip(), "Safety Clarification")

    # Decide web-search usage under strict stop conditions.
    need_web_search, search_query = _decide_web_search(state)
    if need_web_search and search_query:
        web_evidence = _run_web_search(state, search_query)
        if web_evidence:
            source_info = "Current Medical Research & News"
        else:
            source_info = rag_source or f"{domain.capitalize()} AI Coach"
    else:
        source_info = rag_source or f"{domain.capitalize()} AI Coach"

    # Skill shortcut: if user embeds ECG payload, generate ECG report directly.
    ecg_skill_output = _maybe_run_ecg_skill(question, state.get("session_id", ""))
    if ecg_skill_output is not None:
        answer = (
            f"{ecg_skill_output.report}\n\n"
            f"风险等级：{ecg_skill_output.risk_level}\n"
            f"免责声明：{ecg_skill_output.disclaimer}"
        )
        answer = _normalize_answer(answer, question)
        source_info = "ECG Report Skill"
        logger.info("Executor: ECG report skill executed")
        return _finalize_response(state, question, answer, source_info)

    if not llm:
        if domain == "general" and _is_lightweight_chitchat(question):
            answer = "你好，我在。你想聊健康问题、饮食、运动、睡眠，还是心电数据？"
        else:
            answer = (
                "当前医疗助手服务暂时不可用，建议你先进行基础观察，必要时尽快咨询线下医生。"
            )
        source_info = "System Message"
    else:
        prompt = (
            "你是一位温暖、专业且务实的中文私人健康与生活方式教练。\n"
            "输出必须使用简体中文（必要的医学名词可保留英文缩写）。\n"
            "不要过度诊断；证据不足时明确说明不确定性。\n"
            "当用户处于安全状态时，请优先给出能立即执行的小建议，不要写成空泛口号。\n"
            "回答格式必须遵循：\n"
            "1) 用1-2句回应用户当前问题\n"
            "2) 给出1-3条可执行的微小建议\n"
            "3) 最后必须主动追问一个下一步问题，引导继续对话\n"
            "4) 若出现高风险症状，优先提示紧急就医阈值\n\n"
            f"当前领域：{domain}\n"
            f"当前主科室：{primary_department}\n"
            f"硬件心电数据摘要：{ecg_info}\n\n"
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
            answer = _normalize_answer(answer, question)
            state["llm_success"] = bool(answer)
            state["llm_attempted"] = True
            if not state.get("rag_context") and source_info != "Current Medical Research & News":
                source_info = f"{domain.capitalize()} AI Coach"
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
            answer = _normalize_answer(answer, question)
            source_info = "System Message"
            state["llm_success"] = False
            state["llm_attempted"] = True

    if source_info == "System Message":
        answer = _normalize_answer(answer, question)

    return _finalize_response(state, question, answer, source_info)
