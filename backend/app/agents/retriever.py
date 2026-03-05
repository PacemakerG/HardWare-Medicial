"""
MediGenius — agents/retriever.py
RetrieverAgent: retrieves relevant documents from the vector store (RAG).
"""

from app.core.logging_config import logger
from app.core.state import AgentState
from app.tools.vector_store import get_retriever


def RetrieverAgent(state: AgentState) -> AgentState:
    """Retrieve relevant documents from the ChromaDB vector store."""
    retriever = get_retriever()
    if not retriever:
        logger.warning("RAG: No retriever available — vector store not initialized")
        state["documents"] = []
        state["rag_success"] = False
        state["rag_attempted"] = True
        return state

    # Build context-enriched query from recent conversation
    context_parts = [
        f"Context: {item.get('content', '')}"
        for item in state.get("conversation_history", [])[-3:]
        if item.get("role") == "user"
    ]
    context = " | ".join(context_parts)
    combined_query = f"{state['question']} {context}" if context else state["question"]

    docs = retriever.invoke(combined_query)
    valid_docs = [d for d in docs if len(d.page_content.strip()) > 50] if docs else []

    if valid_docs:
        from app.tools.llm_client import get_light_llm
        light_llm = get_light_llm()
        if light_llm:
            doc_contents = "\n".join([d.page_content[:500] for d in valid_docs])
            prompt = (
                f"Question: {combined_query}\n\n"
                f"Context:\n{doc_contents}\n\n"
                "Based on the Context, can you confidently and highly accurately answer the Question? "
                "Reply with ONLY 'YES' or 'NO'."
            )
            try:
                eval_response = light_llm.invoke(prompt)
                if "YES" not in eval_response.content.upper():
                    logger.info("RAG Confidence Check Failed. Discarding docs. Response: %s", eval_response.content)
                    valid_docs = []
            except Exception as e:
                logger.error("RAG Confidence Check Error: %s", e)

    if valid_docs:
        state["documents"] = valid_docs
        state["rag_success"] = True
        state["source"] = "Medical Literature Database"
        logger.info("RAG: Found %d relevant documents", len(valid_docs))
    else:
        state["documents"] = []
        state["rag_success"] = False
        logger.info("RAG: No valid documents found or confidence check failed")

    state["rag_attempted"] = True
    return state
