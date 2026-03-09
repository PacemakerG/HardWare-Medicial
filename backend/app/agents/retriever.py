"""
MediGenius — agents/retriever.py
RetrieverAgent: multi-scope retrieval with department-aware filtering.
"""

from __future__ import annotations

from langchain_core.documents import Document

from app.core.logging_config import logger
from app.core.medical_taxonomy import GENERAL_MEDICAL_DEPARTMENT, department_display_name
from app.core.state import AgentState, append_flow_trace
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
    candidate_queries = [
        department_queries.get(scope),
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
    )


def RetrieverAgent(state: AgentState) -> AgentState:
    """Retrieve documents across one or more scopes and merge raw candidates."""
    append_flow_trace(state, "rag")
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
    documents: list[Document] = []
    merged_rag_context: list[dict] = []
    retrieval_results_by_scope: dict[str, list[dict]] = {}
    seen_docs = set()

    for scope in scopes:
        retriever = get_retriever(
            k=_score_scope_k(scope, primary_department),
            search_kwargs={"filter": _build_scope_filter(scope, domain)},
        )
        if not retriever:
            logger.warning("RAG: No retriever available for scope=%s", scope)
            continue

        scope_results: list[dict] = []
        for query in _scope_queries(state, scope):
            try:
                docs = retriever.invoke(query)
            except Exception as exc:
                logger.error("RAG: Retrieval failed for scope=%s query=%s: %s", scope, query, exc)
                docs = []

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
                chunk = {
                    "content": doc.page_content[:1200],
                    "metadata": doc.metadata or {},
                    "scope": scope,
                    "scope_display_name": department_display_name(scope),
                    "query_used": query,
                    "raw_rank": raw_rank,
                }
                merged_rag_context.append(chunk)
                scope_results.append(chunk)

        retrieval_results_by_scope[scope] = scope_results

    state["documents"] = documents
    state["merged_rag_context"] = merged_rag_context
    state["retrieval_results_by_scope"] = retrieval_results_by_scope
    state["rag_context"] = merged_rag_context[:8]
    state["rag_success"] = bool(merged_rag_context)
    state["rag_attempted"] = True
    if merged_rag_context:
        unique_scopes = [department_display_name(scope) for scope in scopes if retrieval_results_by_scope.get(scope)]
        state["source"] = " + ".join(unique_scopes) + " 知识库" if unique_scopes else "Medical Knowledge Base"
        logger.info(
            "RAG: merged %d chunks across scopes=%s",
            len(merged_rag_context),
            scopes,
        )
    else:
        state["source"] = ""
        logger.info("RAG: No valid documents found for scopes=%s", scopes)
    return state
