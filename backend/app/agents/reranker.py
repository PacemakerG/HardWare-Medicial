"""
MediGenius — agents/reranker.py
Lightweight reranking of merged retrieval results before final generation.
"""

from __future__ import annotations

from typing import List

from app.core.config import (
    RERANKER_FINAL_TOP_K,
    RERANKER_MODEL_WEIGHT,
    RERANKER_RULE_WEIGHT,
    RERANKER_STAGE1_TOP_N,
)
from app.core.medical_taxonomy import extract_query_terms
from app.core.state import AgentState, append_flow_trace, profile_node, set_retrieval_metric
from app.core.langsmith_service import langsmith_traceable
from app.tools.model_reranker import rerank_with_model


def _overlap_score(text: str, terms: list[str]) -> float:
    lowered = (text or "").lower()
    return float(sum(1 for term in terms if term in lowered))


def _normalize_model_scores(scores: List[float]) -> List[float]:
    if not scores:
        return []
    min_v = min(scores)
    max_v = max(scores)
    if abs(max_v - min_v) < 1e-9:
        return [0.5 for _ in scores]
    return [(value - min_v) / (max_v - min_v) for value in scores]


@langsmith_traceable("reranker")
def RerankerAgent(state: AgentState) -> AgentState:
    """Two-stage reranking: fast rule ranking + optional model fine-ranking."""
    append_flow_trace(state, "reranker")
    with profile_node(state, "reranker"):
        candidates = list(state.get("merged_rag_context") or state.get("rag_context") or [])
        if not candidates:
            state["reranked_rag_context"] = []
            state["rag_context"] = []
            return state

        question = state.get("question", "")
        question_terms = extract_query_terms(question)
        retrieval_terms = extract_query_terms(state.get("retrieval_query", "") or question)
        primary_department = state.get("primary_department")
        scope_priority = {
            scope: max(0.5, 3.0 - idx)
            for idx, scope in enumerate(state.get("retrieval_scopes", []))
        }

        rule_ranked = []
        for idx, item in enumerate(candidates):
            content = item.get("content", "")
            metadata = item.get("metadata", {}) or {}
            scope = item.get("scope") or metadata.get("department") or metadata.get("domain")
            score = 0.0
            score += _overlap_score(content, question_terms) * 2.0
            score += _overlap_score(content, retrieval_terms)
            score += scope_priority.get(scope, 0.5)
            if primary_department and scope == primary_department:
                score += 1.5
            raw_rank = int(item.get("raw_rank", idx))
            score += 1.0 / (raw_rank + 1.0)
            # Encourage explicit match between retrieval query and metadata labels.
            if metadata.get("source_book") and any(term in str(metadata.get("source_book", "")).lower() for term in retrieval_terms[:3]):
                score += 0.8
            rule_ranked.append({**item, "rule_score": round(score, 4)})

        rule_ranked.sort(key=lambda item: item.get("rule_score", 0.0), reverse=True)
        stage1_top_n = max(RERANKER_FINAL_TOP_K, RERANKER_STAGE1_TOP_N)
        candidate_pool = rule_ranked[:stage1_top_n]
        rerank_reason = "rule-fast-rerank"

        model_scores = rerank_with_model(
            question,
            [item.get("content", "") for item in candidate_pool],
        )
        if model_scores:
            normalized_model_scores = _normalize_model_scores(model_scores)
            fused = []
            for item, model_score in zip(candidate_pool, normalized_model_scores):
                final_score = (
                    float(item.get("rule_score", 0.0)) * float(RERANKER_RULE_WEIGHT)
                    + float(model_score) * float(RERANKER_MODEL_WEIGHT)
                )
                fused.append(
                    {
                        **item,
                        "model_score": round(float(model_score), 4),
                        "rerank_score": round(final_score, 4),
                    }
                )
            fused.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
            reranked = fused
            rerank_reason = "rule+model-two-stage"
        else:
            reranked = [{**item, "rerank_score": item.get("rule_score", 0.0)} for item in candidate_pool]
            reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)

        final_top_k = max(1, int(RERANKER_FINAL_TOP_K))
        top_context = reranked[:final_top_k]
        state["reranked_rag_context"] = top_context
        state["rag_context"] = top_context
        set_retrieval_metric(state, "rerank_reason", rerank_reason)
        set_retrieval_metric(state, "rerank_stage1_pool", len(candidate_pool))
        set_retrieval_metric(state, "rerank_final_k", len(top_context))
    return state
