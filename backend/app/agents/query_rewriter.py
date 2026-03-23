"""
MediGenius — agents/query_rewriter.py
Rewrite the user question into retrieval-focused queries.
"""

from __future__ import annotations

import json
import re

from app.core.config import (
    QUERY_REWRITER_ENABLED,
    QUERY_REWRITER_MAX_SUBQUERIES,
    QUERY_REWRITER_USE_LLM,
)
from app.core.logging_config import logger
from app.core.medical_taxonomy import (
    GENERAL_MEDICAL_DEPARTMENT,
    department_display_name,
    extract_query_terms,
)
from app.core.state import AgentState, append_flow_trace, profile_node, set_retrieval_metric
from app.core.langsmith_service import langsmith_traceable
from app.tools.llm_client import coerce_response_text, get_light_llm


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def _fallback_retrieval_query(question: str, scope: str | None = None) -> str:
    terms = extract_query_terms(question)
    if scope and scope != GENERAL_MEDICAL_DEPARTMENT:
        terms.insert(0, department_display_name(scope))
    if not terms:
        return question.strip()
    return " ".join(terms[:12])


def _estimate_query_complexity(question: str) -> str:
    text = (question or "").strip()
    if not text:
        return "simple"
    if len(text) >= 32:
        return "complex"
    if len(re.findall(r"[，,；;。？！?]", text)) >= 2:
        return "complex"
    if any(marker in text for marker in ("并且", "同时", "以及", "分别", "可能原因", "鉴别诊断", "治疗方案")):
        return "complex"
    return "simple"


def _dedupe_queries(queries: list[str], max_count: int) -> list[str]:
    unique: list[str] = []
    seen = set()
    for query in queries:
        normalized = str(query or "").strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
        if len(unique) >= max_count:
            break
    return unique


def _decompose_query_heuristic(question: str, max_count: int) -> list[str]:
    base_query = _fallback_retrieval_query(question)
    segments = re.split(r"[，,；;。？！?\n]|并且|以及|同时|然后|再|并发|此外", question or "")
    candidates = [base_query]
    for segment in segments:
        segment = segment.strip()
        if len(segment) < 4:
            continue
        rewritten = _fallback_retrieval_query(segment)
        if rewritten:
            candidates.append(rewritten)
    return _dedupe_queries(candidates, max_count=max_count)


@langsmith_traceable("query_rewriter")
def QueryRewriterAgent(state: AgentState) -> AgentState:
    """Generate retrieval-oriented queries while preserving the original question."""
    append_flow_trace(state, "query_rewriter")
    with profile_node(state, "query_rewriter"):
        question = (state.get("question") or "").strip()
        if not question:
            return state

        domain = state.get("domain", "general")
        forced_department_mode = bool(
            state.get("selected_department_forced") and state.get("selected_department")
        )
        if forced_department_mode:
            scopes = [state["selected_department"]]
        else:
            candidate_departments = [
                item.get("name")
                for item in state.get("department_candidates", [])
                if isinstance(item, dict) and item.get("name")
            ]
            if domain == "medical":
                scopes = candidate_departments[:3] or [state.get("primary_department") or GENERAL_MEDICAL_DEPARTMENT]
            elif state.get("use_rag") or state.get("need_rag"):
                scopes = [domain]
            else:
                scopes = []

        complexity = _estimate_query_complexity(question)
        max_queries = max(1, QUERY_REWRITER_MAX_SUBQUERIES)
        fallback_query = _fallback_retrieval_query(question)
        fallback_queries = _decompose_query_heuristic(question, max_queries)
        fallback_department_queries = {scope: _fallback_retrieval_query(question, scope) for scope in scopes}
        fallback_department_multi_queries = {
            scope: _dedupe_queries([fallback_department_queries.get(scope, fallback_query)] + fallback_queries, max_queries)
            for scope in scopes
        }

        rewrite_reason = "heuristic keyword normalization"
        retrieval_query = fallback_query
        retrieval_queries = fallback_queries
        department_queries = fallback_department_queries
        department_multi_queries = fallback_department_multi_queries

        if not QUERY_REWRITER_ENABLED:
            retrieval_query = question or fallback_query
            retrieval_queries = _dedupe_queries([retrieval_query] + fallback_queries, max_queries)
            department_queries = {scope: retrieval_query for scope in scopes}
            department_multi_queries = {
                scope: _dedupe_queries([retrieval_query] + retrieval_queries, max_queries)
                for scope in scopes
            }
            rewrite_reason = "query rewriter disabled by config"
        elif forced_department_mode:
            retrieval_query = fallback_department_queries.get(scopes[0], fallback_query)
            retrieval_queries = _dedupe_queries([retrieval_query] + fallback_queries, max_queries)
            rewrite_reason = "manual department fast-path"
        elif not QUERY_REWRITER_USE_LLM:
            rewrite_reason = "heuristic keyword normalization (llm disabled)"
        else:
            llm = get_light_llm(
                tenant_id=state.get("tenant_id", "default"),
                user_id=state.get("user_id", "anonymous"),
            )
            if llm and scopes:
                prompt = (
                    "你负责把用户问题改写为更适合医学检索的短语，必要时拆分为多条子查询。\n"
                    "只返回 JSON，不要解释：\n"
                    "{"
                    "\"retrieval_query\": \"...\", "
                    "\"retrieval_queries\": [\"...\"], "
                    "\"department_queries\": {\"scope\": \"...\"}, "
                    "\"department_multi_queries\": {\"scope\": [\"...\"]}, "
                    "\"rewrite_reason\": \"...\""
                    "}\n"
                    "约束：\n"
                    "1) retrieval_queries 最多 3 条，不要写完整答案。\n"
                    "2) 查询语句聚焦症状、检查、诊断、治疗关键词。\n"
                    f"检索范围：{', '.join(scopes)}\n"
                    f"用户问题：{question[:1200]}\n"
                )
                try:
                    raw = llm.invoke(prompt)
                    content = coerce_response_text(raw)
                    parsed = json.loads(_extract_json_block(content))
                    retrieval_query = str(parsed.get("retrieval_query") or fallback_query).strip() or fallback_query
                    raw_queries = parsed.get("retrieval_queries") or []
                    parsed_queries = raw_queries if isinstance(raw_queries, list) else [raw_queries]
                    retrieval_queries = _dedupe_queries(
                        [retrieval_query] + [str(item) for item in parsed_queries] + fallback_queries,
                        max_queries,
                    )

                    raw_department_queries = parsed.get("department_queries") or {}
                    raw_department_multi_queries = parsed.get("department_multi_queries") or {}
                    for scope in scopes:
                        scope_single = raw_department_queries.get(scope)
                        if scope_single:
                            department_queries[scope] = str(scope_single).strip()
                        scope_multi = raw_department_multi_queries.get(scope)
                        if isinstance(scope_multi, list):
                            scope_queries = [str(item).strip() for item in scope_multi if str(item).strip()]
                        elif scope_multi:
                            scope_queries = [str(scope_multi).strip()]
                        else:
                            scope_queries = []
                        department_multi_queries[scope] = _dedupe_queries(
                            [department_queries.get(scope, fallback_query)] + scope_queries + retrieval_queries,
                            max_queries,
                        )
                    rewrite_reason = str(parsed.get("rewrite_reason") or rewrite_reason)
                except Exception as exc:
                    logger.warning("QueryRewriter fallback used: %s", exc)

        if not retrieval_queries:
            retrieval_queries = _dedupe_queries([retrieval_query, fallback_query], max_queries)
        for scope in scopes:
            if scope not in department_multi_queries or not department_multi_queries[scope]:
                department_multi_queries[scope] = _dedupe_queries(
                    [department_queries.get(scope, fallback_query)] + retrieval_queries,
                    max_queries,
                )

        state["retrieval_query"] = retrieval_query
        state["retrieval_queries"] = retrieval_queries
        state["department_queries"] = department_queries
        state["department_multi_queries"] = department_multi_queries
        state["query_complexity"] = complexity
        state["rewrite_reason"] = rewrite_reason
        set_retrieval_metric(state, "query_complexity", complexity)
        set_retrieval_metric(state, "rewrite_reason", rewrite_reason)
        set_retrieval_metric(state, "rewritten_queries", retrieval_queries)
        logger.info(
            "QueryRewriter: query=%s complexity=%s scopes=%s sub_queries=%d",
            retrieval_query[:80],
            complexity,
            list(department_queries.keys()),
            len(retrieval_queries),
        )
    return state
