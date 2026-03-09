"""
MediGenius — tools/pdf_loader.py
PDF document loading and text splitting utilities.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from app.core.medical_taxonomy import (
    GENERAL_MEDICAL_DEPARTMENT,
    normalize_department_code,
)
from app.core.logging_config import logger


def load_pdf(pdf_path: str) -> List[Document]:
    """Load all pages from a PDF file using PyPDFLoader."""
    from langchain_community.document_loaders import PyPDFLoader

    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    logger.info("Loaded %d pages from PDF: %s", len(docs), pdf_path)
    return docs


def split_documents(docs: List[Document]) -> List[Document]:
    """Split documents into overlapping chunks using tiktoken-aware splitter."""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=512,
        chunk_overlap=128,
        separators=["\n\n", ". ", "\n", " "],
    )
    splits = splitter.split_documents(docs)
    logger.info("Split into %d chunks", len(splits))
    return splits


def process_pdf(pdf_path: str) -> List[Document]:
    """Load a PDF and split it into chunks. Convenience wrapper."""
    return split_documents(load_pdf(pdf_path))


def process_pdf_with_metadata(pdf_path: str, metadata: dict | None = None) -> List[Document]:
    """Load and split a PDF, applying shared metadata to each chunk."""
    shared_metadata = dict(metadata or {})
    chunks = process_pdf(pdf_path)
    for chunk in chunks:
        chunk.metadata = {**shared_metadata, **(chunk.metadata or {})}
    return chunks


def _infer_department_from_path(file_path: Path, root_dir: Path) -> str:
    try:
        relative_parts = file_path.relative_to(root_dir).parts
    except ValueError:
        relative_parts = file_path.parts

    for part in relative_parts[:-1]:
        department = normalize_department_code(part)
        if department:
            return department
    return GENERAL_MEDICAL_DEPARTMENT


def process_knowledge_library(root_dir: str) -> List[Document]:
    """Load all PDFs under the knowledge root and attach department metadata."""
    root_path = Path(root_dir)
    if not root_path.exists():
        logger.warning("Knowledge root not found: %s", root_dir)
        return []

    pdf_files = sorted(path for path in root_path.rglob("*.pdf") if path.is_file())
    if not pdf_files:
        logger.warning("No PDF files found under knowledge root: %s", root_dir)
        return []

    all_chunks: List[Document] = []
    failed_files: List[str] = []
    for pdf_file in pdf_files:
        department = _infer_department_from_path(pdf_file, root_path)
        source_book = pdf_file.stem
        try:
            chunks = process_pdf_with_metadata(
                str(pdf_file),
                {
                    "domain": "medical",
                    "department": department,
                    "source_book": source_book,
                    "source_path": str(pdf_file),
                },
            )
        except Exception as exc:
            failed_files.append(os.path.relpath(pdf_file, root_path))
            logger.exception(
                "Knowledge ingest failed: %s -> department=%s (%s)",
                os.path.relpath(pdf_file, root_path),
                department,
                exc,
            )
            continue

        all_chunks.extend(chunks)
        logger.info(
            "Knowledge ingest: %s -> department=%s, chunks=%d",
            os.path.relpath(pdf_file, root_path),
            department,
            len(chunks),
        )

    if failed_files:
        logger.warning(
            "Knowledge ingest completed with %d failed PDF(s): %s",
            len(failed_files),
            failed_files,
        )
    else:
        logger.info("Knowledge ingest completed without PDF failures.")

    return all_chunks
