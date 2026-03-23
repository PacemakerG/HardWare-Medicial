"""
MediGenius — agents/retriever.py
RetrieverAgent: multi-scope retrieval with department-aware filtering.
"""

from __future__ import annotations

from langchain_core.documents import Document

from app.core.config import (
    HYBRID_KEYWORD_TOPK_COMPLEX,
    HYBRID_KEYWORD_TOPK_SIMPLE,
    HYBRID_RETRIEVAL_ENABLED,
    HYBRID_RETRIEVAL_MAX_CONTEXT,
    HYBRID_VECTOR_TOPK_COMPLEX,
    HYBRID_VECTOR_TOPK_SIMPLE,
)
from app.core.logging_config import logger
from app.core.medical_taxonomy import GENERAL_MEDICAL_DEPARTMENT, department_display_name
from app.core.state import AgentState, append_flow_trace, profile_node, set_retrieval_metric
from app.core.langsmith_service import langsmith_traceable
from app.tools.keyword_retriever import keyword_search
from app.tools.vector_store import get_retriever


def _build_scope_filter(scope: str, domain: str) -> dict:
    if domain == "medical":
        if scope == GENERAL_MEDICAL_DEPARTMENT:
            # Keep general scope strict to avoid mixing specialist corpora.
            return {"department": GENERAL_MEDICAL_DEPARTMENT}
        return {"department": scope}
    return {"domain": domain}


def _resolve_scopes(state: AgentState) -> list[str]:
    if state.get("selected_department_forced") and state.get("selected_department"):
        return [state["selected_department"]]

    domain = state.get("domain", "general")
    if domain == "medical":
        scopes = []
        primary_department = state.get("primary_department")
        if primary_department:
            scopes.append(primary_department)
        for item in state.get("department_candidates", []):
            scope = item.get("name") if isinstance(item, dict) else None
            if scope and scope not in scopes:
                scopes.append(scope)
        if GENERAL_MEDICAL_DEPARTMENT not in scopes:
            scopes.append(GENERAL_MEDICAL_DEPARTMENT)
        return scopes[:3]

    if state.get("use_rag") or state.get("need_rag"):
        return [domain]
    return []


def _scope_queries(state: AgentState, scope: str) -> list[str]:
    queries = []
    department_queries = state.get("department_queries") or {}
    department_multi_queries = state.get("department_multi_queries") or {}
    candidate_queries = [
        *(
            department_multi_queries.get(scope)
            if isinstance(department_multi_queries.get(scope), list)
            else []
        ),
        department_queries.get(scope),
        *(state.get("retrieval_queries") or []),
        state.get("retrieval_query"),
        state.get("search_query"),
        state.get("question"),
    ]
    seen = set()
    for query in candidate_queries:
        if not query:
            continue
        normalized = str(query).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        queries.append(normalized)
    return queries


def _score_scope_k(scope: str, primary_department: str | None) -> int:
    if primary_department and scope == primary_department:
        return 4
    if scope == GENERAL_MEDICAL_DEPARTMENT:
        return 2
    return 2


def _doc_key(doc: Document) -> tuple:
    metadata = doc.metadata or {}
    return (
        doc.page_content.strip(),
        metadata.get("source") or metadata.get("source_path"),
        metadata.get("page"),
        metadata.get("parent_chunk_id"),
    )


def _query_complexity(state: AgentState) -> str:
    complexity = (state.get("query_complexity") or "simple").strip().lower()
    return complexity if complexity in {"simple", "complex"} else "simple"


def _resolve_vector_top_k(state: AgentState) -> int:
    return HYBRID_VECTOR_TOPK_COMPLEX if _query_complexity(state) == "complex" else HYBRID_VECTOR_TOPK_SIMPLE


def _resolve_keyword_top_k(state: AgentState) -> int:
    return HYBRID_KEYWORD_TOPK_COMPLEX if _query_complexity(state) == "complex" else HYBRID_KEYWORD_TOPK_SIMPLE


@langsmith_traceable("rag")
def RetrieverAgent(state: AgentState) -> AgentState:
    """Retrieve documents across one or more scopes and merge raw candidates."""
    append_flow_trace(state, "rag")
    with profile_node(state, "rag"):
        domain = state.get("domain", "general")
        scopes = _resolve_scopes(state)
        state["retrieval_scopes"] = scopes

        if not scopes:
            state["documents"] = []
            state["merged_rag_context"] = []
            state["rag_context"] = []
            state["rag_success"] = False
            state["rag_attempted"] = True
            return state

        primary_department = state.get("primary_department")
        vector_top_k = max(1, _resolve_vector_top_k(state))
        keyword_top_k = max(1, _resolve_keyword_top_k(state))
        max_context = max(8, int(HYBRID_RETRIEVAL_MAX_CONTEXT))
        use_keyword = bool(HYBRID_RETRIEVAL_ENABLED and state.get("retrieval_queries"))

        documents: list[Document] = []
        merged_rag_context: list[dict] = []
        retrieval_results_by_scope: dict[str, list[dict]] = {}
        seen_docs = set()
        vector_hits = 0
        keyword_hits = 0
        attempted_queries = 0

        for scope in scopes:
            retriever = get_retriever(
                k=max(vector_top_k, _score_scope_k(scope, primary_department)),
                search_kwargs={"filter": _build_scope_filter(scope, domain)},
            )
            if not retriever:
                logger.warning("RAG: No retriever available for scope=%s", scope)
                continue

            scope_results: list[dict] = []
            for query in _scope_queries(state, scope):
                attempted_queries += 1
                try:
                    vector_docs = retriever.invoke(query)
                except Exception as exc:
                    logger.error("RAG: Vector retrieval failed for scope=%s query=%s: %s", scope, query, exc)
                    vector_docs = []

                methods_payload = [("vector", list(vector_docs or [])[:vector_top_k])]
                if use_keyword:
                    try:
                        keyword_docs = keyword_search(
                            query,
                            scope=scope,
                            domain=domain,
                            top_k=keyword_top_k,
                        )
                    except Exception as exc:
                        logger.warning("RAG: Keyword retrieval failed for scope=%s: %s", scope, exc)
                        keyword_docs = []
                    methods_payload.append(("keyword", keyword_docs))

                for retrieval_method, docs in methods_payload:
                    for raw_rank, doc in enumerate(docs or []):
                        if not isinstance(doc, Document):
                            continue
                        if len(doc.page_content.strip()) <= 50:
                            continue

                        doc_key = _doc_key(doc)
                        if doc_key in seen_docs:
                            continue
                        seen_docs.add(doc_key)
                        documents.append(doc)
                        if retrieval_method == "vector":
                            vector_hits += 1
                        else:
                            keyword_hits += 1
                        chunk = {
                            "content": doc.page_content[:1400],
                            "metadata": doc.metadata or {},
                            "scope": scope,
                            "scope_display_name": department_display_name(scope),
                            "query_used": query,
                            "raw_rank": raw_rank,
                            "retrieval_method": retrieval_method,
                        }
                        merged_rag_context.append(chunk)
                        scope_results.append(chunk)
                        if len(merged_rag_context) >= max_context:
                            break
                    if len(merged_rag_context) >= max_context:
                        break
                if len(merged_rag_context) >= max_context:
                    break
            retrieval_results_by_scope[scope] = scope_results
            if len(merged_rag_context) >= max_context:
                break

        state["documents"] = documents
        state["merged_rag_context"] = merged_rag_context
        state["retrieval_results_by_scope"] = retrieval_results_by_scope
        state["rag_context"] = merged_rag_context[:8]
        state["rag_success"] = bool(merged_rag_context)
        state["rag_attempted"] = True
        set_retrieval_metric(state, "scopes", scopes)
        set_retrieval_metric(state, "attempted_queries", attempted_queries)
        set_retrieval_metric(state, "vector_hits", vector_hits)
        set_retrieval_metric(state, "keyword_hits", keyword_hits)
        set_retrieval_metric(state, "merged_chunks", len(merged_rag_context))
        if merged_rag_context:
            unique_scopes = [department_display_name(scope) for scope in scopes if retrieval_results_by_scope.get(scope)]
            state["source"] = " + ".join(unique_scopes) + " 知识库" if unique_scopes else "Medical Knowledge Base"
            logger.info(
                "RAG: merged=%d scopes=%s vector_hits=%d keyword_hits=%d",
                len(merged_rag_context),
                scopes,
                vector_hits,
                keyword_hits,
            )
        else:
            state["source"] = ""
            logger.info("RAG: No valid documents found for scopes=%s", scopes)
    return state
