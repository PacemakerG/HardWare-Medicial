"""
MediGenius Backend — main.py
FastAPI application entry point: app setup, lifespan, and router registration.

Module layout:
  core/               — config, logging, state, workflow
  agents/             — 8 individual LangGraph agent nodes
  tools/              — LLM client, vector store, PDF loader, search tools
  db/                 — SQLAlchemy session factory
  models/             — ORM models
  schemas/            — Pydantic request/response schemas
  services/           — DatabaseService, ChatService
  api/v1/endpoints/   — health, chat, session route handlers
  api/v1/api.py       — router aggregator
  main.py             — FastAPI app + lifespan  ← you are here
"""

import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.api.v1.api import api_router
from app.core.config import (
    CHAT_DB_PATH,
    KEYWORD_BACKEND,
    KNOWLEDGE_ROOT_DIR,
    PDF_PATH,
    RAG_ENABLED,
    VECTOR_STORE_DIR,
)
from app.core.logging_config import logger
from app.services.chat_service import chat_service
from app.services.database_service import db_service
from app.core.langsmith_service import configure_langsmith
from app.tools.es_client import bulk_index_documents, es_document_count, es_enabled
from app.tools.pdf_loader import (
    GENERAL_MEDICAL_DEPARTMENT,
    process_knowledge_library,
    process_pdf,
    process_pdf_with_metadata,
)
from app.tools.vector_store import get_or_create_vectorstore


# ── Lifespan ───────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("Initializing MediGenius System...")
    configure_langsmith()
    knowledge_docs = None

    db_service.init_db()
    logger.info("Database initialized at %s", CHAT_DB_PATH)

    if RAG_ENABLED:
        try:
            # Fast path: reuse persisted Chroma directly on restart.
            vectorstore = get_or_create_vectorstore()
            if vectorstore:
                logger.info("Vector store loaded from persistence at %s", VECTOR_STORE_DIR)
            else:
                knowledge_docs = process_knowledge_library(KNOWLEDGE_ROOT_DIR)
                if knowledge_docs:
                    logger.info("Processing knowledge library: %s", KNOWLEDGE_ROOT_DIR)
                    vectorstore = get_or_create_vectorstore(knowledge_docs)
                    if vectorstore:
                        logger.info("Vector store ready at %s", VECTOR_STORE_DIR)
                    else:
                        logger.warning(
                            "Vector store initialization skipped/failed. System will continue without RAG."
                        )
                elif os.path.exists(PDF_PATH):
                    logger.info("Processing PDF: %s", PDF_PATH)
                    documents = process_pdf(PDF_PATH)
                    vectorstore = get_or_create_vectorstore(documents)
                    if vectorstore:
                        logger.info("Vector store ready at %s", VECTOR_STORE_DIR)
                    else:
                        logger.warning(
                            "Vector store initialization skipped/failed. System will continue without RAG."
                        )
                else:
                    logger.warning("PDF not found at %s — vector store skipped", PDF_PATH)
        except Exception as exc:
            logger.error("RAG initialization failed: %s", exc)
            logger.warning("System will continue without RAG support.")
    else:
        logger.info("RAG initialization disabled by RAG_ENABLED=false")

    if es_enabled() and KEYWORD_BACKEND == "elasticsearch":
        try:
            if knowledge_docs:
                bulk_index_documents(knowledge_docs)
            elif es_document_count() == 0:
                logger.info("Elasticsearch keyword index empty; backfilling knowledge documents")
                knowledge_docs = process_knowledge_library(KNOWLEDGE_ROOT_DIR)
                if not knowledge_docs and os.path.exists(PDF_PATH):
                    knowledge_docs = process_pdf_with_metadata(
                        PDF_PATH,
                        {
                            "tenant_id": "default",
                            "domain": "medical",
                            "department": GENERAL_MEDICAL_DEPARTMENT,
                            "source_book": Path(PDF_PATH).stem,
                            "source_path": PDF_PATH,
                            "source_type": "pdf",
                        },
                    )
                if knowledge_docs:
                    bulk_index_documents(knowledge_docs)
                else:
                    logger.warning("No documents available to populate Elasticsearch keyword index")
        except Exception as exc:
            logger.warning("Elasticsearch startup sync skipped: %s", exc)

    chat_service.initialize_workflow()
    logger.info("MediGenius System Ready!")

    yield

    logger.info("Shutting down MediGenius...")


# ── FastAPI App ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="MediGenius API",
    description="AI-powered medical consultation system — Deep Modular + Agentic Architecture",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SessionMiddleware, secret_key=secrets.token_hex(32))

# Register all API routes
app.include_router(api_router)


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
