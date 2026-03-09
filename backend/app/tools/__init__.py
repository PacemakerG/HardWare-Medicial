"""
MediGenius — tools/__init__.py
Exports all tool getter functions.
"""

from app.tools.llm_client import get_llm
from app.tools.pdf_loader import (
    load_document,
    load_epub,
    load_pdf,
    process_document,
    process_document_with_metadata,
    process_epub,
    process_epub_with_metadata,
    process_knowledge_library,
    process_pdf,
    process_pdf_with_metadata,
    split_documents,
)
from app.tools.tavily_search import get_tavily_search
from app.tools.vector_store import (
    get_embeddings,
    get_or_create_vectorstore,
    get_retriever,
)
from app.tools.wikipedia_search import get_wikipedia_wrapper

__all__ = [
    "get_llm",
    "get_embeddings",
    "get_or_create_vectorstore",
    "get_retriever",
    "load_document",
    "load_epub",
    "load_pdf",
    "split_documents",
    "process_document",
    "process_document_with_metadata",
    "process_epub",
    "process_epub_with_metadata",
    "process_pdf",
    "process_pdf_with_metadata",
    "process_knowledge_library",
    "get_wikipedia_wrapper",
    "get_tavily_search",
]
