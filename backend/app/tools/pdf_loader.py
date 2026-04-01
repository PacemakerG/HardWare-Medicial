"""
MediGenius — tools/pdf_loader.py
Knowledge document loading and text splitting utilities.
"""

from __future__ import annotations

import os
import posixpath
import re
import hashlib
import xml.etree.ElementTree as ET
import zipfile
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import List

from langchain_core.documents import Document

from app.core.config import (
    RAG_CHILD_CHUNK_OVERLAP,
    RAG_CHILD_CHUNK_SIZE,
    RAG_CHUNK_OVERLAP,
    RAG_CHUNK_SIZE,
    RAG_CHUNK_STRATEGY,
    RAG_PARENT_CHUNK_OVERLAP,
    RAG_PARENT_CHUNK_SIZE,
    RAG_PARENT_CHILD_ENABLED,
)
from app.core.medical_taxonomy import (
    GENERAL_MEDICAL_DEPARTMENT,
    normalize_department_code,
)
from app.core.logging_config import logger

SUPPORTED_KNOWLEDGE_SUFFIXES = (".pdf", ".epub")
EPUB_CONTENT_MEDIA_TYPES = {"application/xhtml+xml", "text/html"}
EPUB_CONTAINER_PATH = "META-INF/container.xml"
BLOCK_TAGS = {
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "figcaption",
    "figure",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: List[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:  # type: ignore[override]
        if tag in {"br", "hr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:  # type: ignore[override]
        if tag in BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:  # type: ignore[override]
        if data:
            self._parts.append(data)

    def get_text(self) -> str:
        return _normalize_text("".join(self._parts))


def load_pdf(pdf_path: str) -> List[Document]:
    """Load all pages from a PDF file using PyPDFLoader."""
    from langchain_community.document_loaders import PyPDFLoader

    loader = PyPDFLoader(pdf_path)
    docs = loader.load()
    logger.info("Loaded %d pages from PDF: %s", len(docs), pdf_path)
    return docs


def _normalize_text(text: str) -> str:
    text = unescape(text).replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(segment.split()) for segment in text.split("\n")]
    normalized = "\n".join(line for line in lines if line)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _hash_identity(*parts: object) -> str:
    payload = "||".join(str(part or "") for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def _stable_parent_chunk_id(parent_doc: Document, parent_idx: int) -> str:
    metadata = parent_doc.metadata or {}
    return (
        "pc-"
        + _hash_identity(
            metadata.get("source_path") or metadata.get("source"),
            metadata.get("page"),
            metadata.get("section"),
            metadata.get("section_index"),
            parent_idx,
            (parent_doc.page_content or "")[:240],
        )
    )


def _stable_chunk_id(chunk: Document) -> str:
    metadata = chunk.metadata or {}
    return (
        "ck-"
        + _hash_identity(
            metadata.get("source_path") or metadata.get("source"),
            metadata.get("source_type"),
            metadata.get("page"),
            metadata.get("section"),
            metadata.get("section_index"),
            metadata.get("chunk_strategy"),
            metadata.get("chunk_level"),
            metadata.get("parent_chunk_id"),
            metadata.get("parent_index"),
            metadata.get("child_index"),
            metadata.get("chunk_index"),
            (chunk.page_content or "")[:320],
        )
    )


def _apply_chunk_identity(chunks: List[Document]) -> List[Document]:
    for chunk in chunks:
        metadata = dict(chunk.metadata or {})
        metadata["chunk_id"] = _stable_chunk_id(chunk)
        chunk.metadata = metadata
    return chunks


def _extract_epub_text(raw_content: bytes) -> str:
    try:
        root = ET.fromstring(raw_content)
        text = "\n".join(part.strip() for part in root.itertext() if part and part.strip())
        return _normalize_text(text)
    except ET.ParseError:
        parser = _HTMLTextExtractor()
        parser.feed(raw_content.decode("utf-8", errors="ignore"))
        parser.close()
        return parser.get_text()


def _get_epub_package_path(archive: zipfile.ZipFile) -> str:
    container_xml = archive.read(EPUB_CONTAINER_PATH)
    container_root = ET.fromstring(container_xml)
    rootfile = container_root.find(".//{*}rootfile")
    if rootfile is None:
        raise ValueError("EPUB missing rootfile declaration")

    package_path = rootfile.attrib.get("full-path")
    if not package_path:
        raise ValueError("EPUB rootfile missing full-path")
    return package_path


def _list_epub_content_paths(archive: zipfile.ZipFile, package_path: str) -> List[str]:
    package_xml = archive.read(package_path)
    package_root = ET.fromstring(package_xml)
    package_dir = posixpath.dirname(package_path)

    manifest = {}
    for item in package_root.findall(".//{*}manifest/{*}item"):
        item_id = item.attrib.get("id")
        href = item.attrib.get("href")
        media_type = item.attrib.get("media-type")
        if item_id and href:
            manifest[item_id] = {
                "href": href.split("#", 1)[0],
                "media_type": media_type or "",
            }

    ordered_paths: List[str] = []
    for itemref in package_root.findall(".//{*}spine/{*}itemref"):
        idref = itemref.attrib.get("idref")
        manifest_item = manifest.get(idref or "")
        if not manifest_item:
            continue
        if manifest_item["media_type"] not in EPUB_CONTENT_MEDIA_TYPES:
            continue
        ordered_paths.append(
            posixpath.normpath(posixpath.join(package_dir, manifest_item["href"]))
        )

    if ordered_paths:
        return ordered_paths

    fallback_paths: List[str] = []
    for item in manifest.values():
        if item["media_type"] not in EPUB_CONTENT_MEDIA_TYPES:
            continue
        fallback_paths.append(posixpath.normpath(posixpath.join(package_dir, item["href"])))
    return fallback_paths


def load_epub(epub_path: str) -> List[Document]:
    """Load EPUB chapters/sections in spine order using the standard library."""
    docs: List[Document] = []
    with zipfile.ZipFile(epub_path) as archive:
        package_path = _get_epub_package_path(archive)
        content_paths = _list_epub_content_paths(archive, package_path)

        for index, content_path in enumerate(content_paths, start=1):
            raw_content = archive.read(content_path)
            text = _extract_epub_text(raw_content)
            if not text:
                continue
            docs.append(
                Document(
                    page_content=text,
                    metadata={
                        "source": epub_path,
                        "section": content_path,
                        "page": index,
                    },
                )
            )

    logger.info("Loaded %d sections from EPUB: %s", len(docs), epub_path)
    return docs


def load_document(document_path: str) -> List[Document]:
    """Load a supported knowledge document based on its file suffix."""
    suffix = Path(document_path).suffix.lower()
    if suffix == ".pdf":
        return load_pdf(document_path)
    if suffix == ".epub":
        return load_epub(document_path)
    raise ValueError(f"Unsupported knowledge document type: {document_path}")


def _build_splitter(chunk_size: int, chunk_overlap: int):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=max(128, int(chunk_size)),
        chunk_overlap=max(0, int(chunk_overlap)),
        separators=["\n\n", ". ", "\n", " "],
    )


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) > 80:
        return False
    heading_patterns = (
        r"^第[一二三四五六七八九十百千0-9]+[章节篇部分卷].*",
        r"^[0-9]+(\.[0-9]+)*\s+.+",
        r"^[（(]?[一二三四五六七八九十0-9]+[）)]\s*.+",
        r"^(chapter|section)\s+[0-9ivx]+",
    )
    lowered = stripped.lower()
    return any(re.match(pattern, stripped) for pattern in heading_patterns) or any(
        lowered.startswith(prefix) for prefix in ("chapter ", "section ", "part ")
    )


def _structured_sections(text: str) -> List[str]:
    lines = [line.strip() for line in (text or "").splitlines()]
    sections: List[str] = []
    buffer: List[str] = []

    for line in lines:
        if not line:
            continue
        if _is_heading_line(line) and buffer:
            section_text = "\n".join(buffer).strip()
            if section_text:
                sections.append(section_text)
            buffer = [line]
            continue
        buffer.append(line)

    if buffer:
        section_text = "\n".join(buffer).strip()
        if section_text:
            sections.append(section_text)
    return sections or [text.strip()]


def _adaptive_child_chunk_size(text: str) -> int:
    length = len(text or "")
    if length <= 900:
        return max(240, min(RAG_CHILD_CHUNK_SIZE, 360))
    if length <= 2200:
        return max(360, RAG_CHILD_CHUNK_SIZE)
    return max(RAG_CHILD_CHUNK_SIZE, min(900, int(RAG_CHILD_CHUNK_SIZE * 1.25)))


def _prepare_structured_docs(docs: List[Document]) -> List[Document]:
    prepared: List[Document] = []
    for doc in docs:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        sections = _structured_sections(text)
        if len(sections) == 1:
            prepared.append(doc)
            continue
        for section_idx, section in enumerate(sections, start=1):
            metadata = dict(doc.metadata or {})
            metadata["section_index"] = section_idx
            prepared.append(Document(page_content=section, metadata=metadata))
    return prepared


def _split_fixed(docs: List[Document]) -> List[Document]:
    splitter = _build_splitter(RAG_CHUNK_SIZE, RAG_CHUNK_OVERLAP)
    split_docs = splitter.split_documents(docs)
    for chunk_idx, split_doc in enumerate(split_docs, start=1):
        metadata = dict(split_doc.metadata or {})
        metadata.setdefault("chunk_strategy", "fixed")
        metadata.setdefault("chunk_index", chunk_idx)
        split_doc.metadata = metadata
    return split_docs


def _split_adaptive(docs: List[Document]) -> List[Document]:
    chunks: List[Document] = []
    for doc in docs:
        chunk_size = _adaptive_child_chunk_size(doc.page_content)
        chunk_overlap = min(RAG_CHILD_CHUNK_OVERLAP, max(32, int(chunk_size * 0.3)))
        splitter = _build_splitter(chunk_size, chunk_overlap)
        split_docs = splitter.split_documents([doc])
        for chunk_idx, child in enumerate(split_docs, start=1):
            metadata = dict(child.metadata or {})
            metadata["chunk_strategy"] = "adaptive"
            metadata["chunk_index"] = chunk_idx
            child.metadata = metadata
            chunks.append(child)
    return chunks


def _split_parent_child(docs: List[Document]) -> List[Document]:
    parent_splitter = _build_splitter(RAG_PARENT_CHUNK_SIZE, RAG_PARENT_CHUNK_OVERLAP)
    child_chunks: List[Document] = []

    for doc in docs:
        parent_docs = parent_splitter.split_documents([doc])
        for parent_idx, parent_doc in enumerate(parent_docs, start=1):
            parent_text = (parent_doc.page_content or "").strip()
            if not parent_text:
                continue
            parent_id = _stable_parent_chunk_id(parent_doc, parent_idx)
            child_size = _adaptive_child_chunk_size(parent_text)
            child_overlap = min(RAG_CHILD_CHUNK_OVERLAP, max(40, int(child_size * 0.28)))
            child_splitter = _build_splitter(child_size, child_overlap)
            split_children = child_splitter.split_documents([parent_doc])
            for child_idx, child_doc in enumerate(split_children, start=1):
                metadata = dict(child_doc.metadata or {})
                metadata["chunk_strategy"] = "parent_child"
                metadata["chunk_level"] = "child"
                metadata["parent_chunk_id"] = parent_id
                metadata["parent_index"] = parent_idx
                metadata["child_index"] = child_idx
                metadata["parent_excerpt"] = parent_text[:900]
                child_doc.metadata = metadata
                child_chunks.append(child_doc)
    return child_chunks


def split_documents(docs: List[Document]) -> List[Document]:
    """Split documents with configurable strategy (fixed/adaptive/parent-child)."""
    if not docs:
        return []

    strategy = (RAG_CHUNK_STRATEGY or "adaptive").strip().lower()
    structured_docs = _prepare_structured_docs(docs) if strategy != "fixed" else docs

    if strategy == "fixed":
        splits = _split_fixed(structured_docs)
    elif RAG_PARENT_CHILD_ENABLED:
        splits = _split_parent_child(structured_docs)
    else:
        splits = _split_adaptive(structured_docs)

    logger.info(
        "Split into %d chunks (strategy=%s, parent_child=%s)",
        len(splits),
        strategy,
        RAG_PARENT_CHILD_ENABLED,
    )
    return _apply_chunk_identity(splits)


def process_pdf(pdf_path: str) -> List[Document]:
    """Load a PDF and split it into chunks. Convenience wrapper."""
    return process_document(pdf_path)


def process_pdf_with_metadata(pdf_path: str, metadata: dict | None = None) -> List[Document]:
    """Load and split a PDF, applying shared metadata to each chunk."""
    return process_document_with_metadata(pdf_path, metadata)


def process_epub(epub_path: str) -> List[Document]:
    """Load an EPUB and split it into chunks. Convenience wrapper."""
    return process_document(epub_path)


def process_epub_with_metadata(epub_path: str, metadata: dict | None = None) -> List[Document]:
    """Load and split an EPUB, applying shared metadata to each chunk."""
    return process_document_with_metadata(epub_path, metadata)


def process_document(document_path: str) -> List[Document]:
    """Load a supported document and split it into chunks."""
    return split_documents(load_document(document_path))


def process_document_with_metadata(
    document_path: str,
    metadata: dict | None = None,
) -> List[Document]:
    """Load and split a supported document, applying shared metadata to each chunk."""
    shared_metadata = dict(metadata or {})
    chunks = process_document(document_path)
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
    """Load supported knowledge documents under the root and attach department metadata."""
    root_path = Path(root_dir)
    if not root_path.exists():
        logger.warning("Knowledge root not found: %s", root_dir)
        return []

    knowledge_files = sorted(
        path
        for path in root_path.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_KNOWLEDGE_SUFFIXES
    )
    if not knowledge_files:
        logger.warning(
            "No supported knowledge files found under knowledge root: %s", root_dir
        )
        return []

    all_chunks: List[Document] = []
    failed_files: List[str] = []
    for knowledge_file in knowledge_files:
        department = _infer_department_from_path(knowledge_file, root_path)
        source_book = knowledge_file.stem
        source_type = knowledge_file.suffix.lower().lstrip(".")
        try:
            chunks = process_document_with_metadata(
                str(knowledge_file),
                {
                    "domain": "medical",
                    "department": department,
                    "source_book": source_book,
                    "source_path": str(knowledge_file),
                    "source_type": source_type,
                },
            )
        except Exception as exc:
            failed_files.append(os.path.relpath(knowledge_file, root_path))
            logger.exception(
                "Knowledge ingest failed: %s -> department=%s (%s)",
                os.path.relpath(knowledge_file, root_path),
                department,
                exc,
            )
            continue

        all_chunks.extend(chunks)
        logger.info(
            "Knowledge ingest: %s -> department=%s, type=%s, chunks=%d",
            os.path.relpath(knowledge_file, root_path),
            department,
            source_type,
            len(chunks),
        )

    if failed_files:
        logger.warning(
            "Knowledge ingest completed with %d failed file(s): %s",
            len(failed_files),
            failed_files,
        )
    else:
        logger.info("Knowledge ingest completed without file failures.")

    return all_chunks
