"""
MediGenius — agents/reranker.py
Lightweight reranking of merged retrieval results before final generation.
"""

from __future__ import annotations

from app.core.medical_taxonomy import extract_query_terms
from app.core.state import AgentState, append_flow_trace


def _overlap_score(text: str, terms: list[str]) -> float:
    lowered = (text or "").lower()
    return float(sum(1 for term in terms if term in lowered))


def RerankerAgent(state: AgentState) -> AgentState:
    """Rerank merged retrieval candidates using query overlap and scope priority."""
    append_flow_trace(state, "reranker")
    candidates = list(state.get("merged_rag_context") or state.get("rag_context") or [])
    if not candidates:
        state["reranked_rag_context"] = []
        state["rag_context"] = []
        return state

    question_terms = extract_query_terms(state.get("question", ""))
    retrieval_terms = extract_query_terms(state.get("retrieval_query", "") or state.get("question", ""))
    primary_department = state.get("primary_department")
    scope_priority = {
        scope: max(0.5, 3.0 - idx)
        for idx, scope in enumerate(state.get("retrieval_scopes", []))
    }

    reranked = []
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
        reranked.append({**item, "rerank_score": round(score, 4)})

    reranked.sort(key=lambda item: item.get("rerank_score", 0.0), reverse=True)
    top_context = reranked[:6]
    state["reranked_rag_context"] = top_context
    state["rag_context"] = top_context
    return state
