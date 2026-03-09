"""
MediGenius — agents/planner.py
HealthConciergeAgent: multi-level safety check and domain classification.
"""

import json

from app.core.logging_config import logger
from app.core.medical_taxonomy import (
    GENERAL_MEDICAL_DEPARTMENT,
    department_display_name,
)
from app.core.state import AgentState, append_flow_trace
from app.tools.llm_client import coerce_response_text, get_light_llm

SENSITIVE_KEYWORDS = [
    "痛",
    "血",
    "呼吸困难",
    "呼吸急促",
    "胸痛",
    "晕",
    "昏",
    "急救",
    "死",
    "严重",
    "救命",
    "pain",
    "bleed",
    "bleeding",
    "shortness of breath",
    "emergency",
    "suicide",
    "hurt",
]

DOMAIN_KEYWORDS = {
    "medical": [
        "发烧",
        "疼痛",
        "胸痛",
        "头痛",
        "症状",
        "药",
        "用药",
        "疾病",
        "诊断",
        "治疗",
        "医院",
        "doctor",
        "medication",
        "symptom",
        "treatment",
        "diagnosis",
    ],
    "nutrition": [
        "饮食",
        "营养",
        "热量",
        "蛋白质",
        "减脂",
        "增肌餐",
        "碳水",
        "脂肪",
        "补剂",
        "diet",
        "nutrition",
        "calorie",
        "protein",
    ],
    "fitness": [
        "运动",
        "健身",
        "训练",
        "跑步",
        "力量",
        "有氧",
        "拉伸",
        "步数",
        "workout",
        "fitness",
        "exercise",
        "cardio",
        "strength",
    ],
    "sleep": [
        "睡眠",
        "失眠",
        "焦虑",
        "压力",
        "心理",
        "情绪",
        "作息",
        "熬夜",
        "sleep",
        "insomnia",
        "stress",
        "anxiety",
        "mood",
    ],
}

RAG_DOMAINS = {"medical", "nutrition", "fitness", "sleep"}


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def _fallback_domain(question: str) -> str:
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if any(keyword in question for keyword in keywords):
            return domain
    return "general"


def HealthConciergeAgent(state: AgentState) -> AgentState:
    """Run a safety-first triage and route SAFE queries by domain."""
    append_flow_trace(state, "health_concierge")
    raw_question = (state.get("question") or "").strip()
    question = raw_question.lower()
    llm = get_light_llm(
        tenant_id=state.get("tenant_id", "default"),
        user_id=state.get("user_id", "anonymous"),
    )
    sensitive_hit = any(keyword in question for keyword in SENSITIVE_KEYWORDS)

    state["keyword_hit"] = sensitive_hit
    state["safety_level"] = "SAFE"
    state["domain"] = "general"
    state["use_rag"] = False
    state["current_tool"] = "judge_need_rag"
    state["retry_count"] = 0
    state["primary_department"] = None
    state["department_candidates"] = []
    state["department_queries"] = {}
    state["retrieval_scopes"] = []
    state["routing_reason"] = ""
    state["rewrite_reason"] = ""

    if sensitive_hit and llm:
        safety_prompt = (
            "你是一个严格的医疗安全护盾。分析患者输入，输出 JSON："
            '{"safety_level": "..."}。\n'
            "- EMERGENCY: 正在发生的、危及生命的急症，如剧烈胸痛、大出血、明显呼吸困难。\n"
            "- CLARIFY: 提及了敏感症状，但是否急症不明确，需要先追问。\n"
            "- SAFE: 纯讨论、无关本人健康，或明显不是现实医疗风险。\n\n"
            f"患者输入：{raw_question}"
        )
        try:
            result = llm.invoke(safety_prompt)
            content = coerce_response_text(result)
            parsed = json.loads(_extract_json_block(content))
            state["safety_level"] = parsed.get("safety_level", "CLARIFY")
            logger.info(
                "HealthConcierge: safety keyword triggered, safety_level=%s",
                state["safety_level"],
            )
        except Exception as exc:
            logger.warning("HealthConcierge: safety triage failed, fallback to CLARIFY: %s", exc)
            state["safety_level"] = "CLARIFY"
    elif sensitive_hit:
        state["safety_level"] = "CLARIFY"

    if state["safety_level"] in {"EMERGENCY", "CLARIFY"}:
        state["current_tool"] = "executor"
        return state

    selected_department = state.get("selected_department")
    if state.get("selected_department_forced") and selected_department:
        state["domain"] = "medical"
        state["use_rag"] = True
        state["primary_department"] = selected_department
        state["department_candidates"] = [
            {
                "name": selected_department,
                "score": 1.0,
                "display_name": department_display_name(selected_department),
            }
        ]
        state["routing_reason"] = (
            "manual department override"
            if selected_department != GENERAL_MEDICAL_DEPARTMENT
            else "manual general-medical override"
        )
        state["current_tool"] = "query_rewriter"
        logger.info(
            "HealthConcierge: manual department override=%s",
            selected_department,
        )
        return state

    domain = _fallback_domain(question)
    if llm:
        domain_prompt = (
            "你是一个健康管家。判断用户输入属于哪个领域，输出 JSON："
            '{"domain": "..."}。\n'
            "可选值只有：medical, nutrition, fitness, sleep, general。\n"
            "medical 表示疾病/症状/检查/用药；nutrition 表示饮食/热量/营养；"
            "fitness 表示运动/训练；sleep 表示睡眠/心理压力；general 表示日常闲聊。\n\n"
            f"用户输入：{raw_question}"
        )
        try:
            result = llm.invoke(domain_prompt)
            content = coerce_response_text(result)
            parsed = json.loads(_extract_json_block(content))
            llm_domain = parsed.get("domain", domain)
            if llm_domain in RAG_DOMAINS or llm_domain == "general":
                domain = llm_domain
        except Exception as exc:
            logger.warning("HealthConcierge: domain classification fallback used: %s", exc)

    state["domain"] = domain
    state["use_rag"] = domain in RAG_DOMAINS
    if domain == "medical":
        state["current_tool"] = "medical_router"
    elif state["use_rag"]:
        state["current_tool"] = "query_rewriter"
    else:
        state["current_tool"] = "judge_need_rag"
    logger.info(
        "HealthConcierge: domain=%s, use_rag=%s",
        state["domain"],
        state["use_rag"],
    )
    return state


KeywordRouterAgent = HealthConciergeAgent
PlannerAgent = HealthConciergeAgent
