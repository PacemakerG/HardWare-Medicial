"""
MediGenius — agents/medical_router.py
Route medical questions to one or more likely hospital departments.
"""

from __future__ import annotations

import json

from app.core.logging_config import logger
from app.core.medical_taxonomy import (
    GENERAL_MEDICAL_DEPARTMENT,
    department_display_name,
    infer_department_candidates,
    list_department_codes,
    normalize_department_code,
)
from app.core.state import AgentState, append_flow_trace, profile_node
from app.core.langsmith_service import langsmith_traceable
from app.tools.llm_client import coerce_response_text, get_light_llm


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def _normalize_candidates(raw_candidates, fallback_candidates: list[dict]) -> list[dict]:
    normalized = []
    seen = set()
    for item in raw_candidates or []:
        if isinstance(item, dict):
            code = normalize_department_code(item.get("name") or item.get("department"))
            score = item.get("score", 0.0)
        else:
            code = normalize_department_code(str(item))
            score = 0.0

        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(
            {
                "name": code,
                "score": float(score) if isinstance(score, (int, float)) else 0.0,
                "display_name": department_display_name(code),
            }
        )

    if not normalized:
        return fallback_candidates

    normalized.sort(key=lambda item: item["score"], reverse=True)
    return normalized[:3]


@langsmith_traceable("medical_router")
def MedicalRouterAgent(state: AgentState) -> AgentState:
    """Classify medical queries into a primary department and candidate departments."""
    append_flow_trace(state, "medical_router")
    with profile_node(state, "medical_router"):
        if state.get("domain") != "medical":
            return state
        if state.get("selected_department_forced") and state.get("selected_department"):
            selected = state["selected_department"]
            state["primary_department"] = selected
            state["department_candidates"] = [
                {
                    "name": selected,
                    "score": 1.0,
                    "display_name": department_display_name(selected),
                }
            ]
            state["routing_reason"] = "manual department override"
            state["current_tool"] = "query_rewriter"
            return state

        question = (state.get("question") or "").strip()
        fallback_candidates = infer_department_candidates(question, top_k=3)
        fallback_primary = fallback_candidates[0]["name"] if fallback_candidates else GENERAL_MEDICAL_DEPARTMENT
        primary_department = fallback_primary
        department_candidates = fallback_candidates
        routing_reason = "heuristic keyword fallback"

        llm = get_light_llm(
            tenant_id=state.get("tenant_id", "default"),
            user_id=state.get("user_id", "anonymous"),
        )
        if llm:
            allowed_departments = ", ".join(code for code in list_department_codes() if code != GENERAL_MEDICAL_DEPARTMENT)
            prompt = (
                "你负责把医疗问题路由到医院科室。\n"
                "只返回如下 JSON：\n"
                "{"
                "\"primary_department\": \"...\", "
                "\"department_candidates\": [{\"name\": \"...\", \"score\": 0.0}], "
                "\"routing_reason\": \"...\""
                "}\n"
                f"允许的科室代码：{allowed_departments}。\n"
                "最多给出 3 个候选科室，score 取值范围必须在 0 到 1 之间。\n"
                f"用户问题：{question[:1200]}\n"
            )
            try:
                raw = llm.invoke(prompt)
                content = coerce_response_text(raw)
                parsed = json.loads(_extract_json_block(content))
                primary = normalize_department_code(parsed.get("primary_department"))
                department_candidates = _normalize_candidates(
                    parsed.get("department_candidates"),
                    fallback_candidates,
                )
                if primary:
                    primary_department = primary
                elif department_candidates:
                    primary_department = department_candidates[0]["name"]
                routing_reason = str(parsed.get("routing_reason") or routing_reason)
            except Exception as exc:
                logger.warning("MedicalRouter fallback used: %s", exc)

        if primary_department not in {item["name"] for item in department_candidates}:
            department_candidates.insert(
                0,
                {
                    "name": primary_department,
                    "score": 0.8,
                    "display_name": department_display_name(primary_department),
                },
            )

        state["primary_department"] = primary_department or GENERAL_MEDICAL_DEPARTMENT
        state["department_candidates"] = department_candidates[:3]
        state["routing_reason"] = routing_reason
        state["current_tool"] = "query_rewriter"
        logger.info(
            "MedicalRouter: primary=%s candidates=%s",
            state["primary_department"],
            [item["name"] for item in state["department_candidates"]],
        )
    return state
