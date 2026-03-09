"""Tests for tools — Deep Modular Architecture"""
import os
import sys
from unittest.mock import MagicMock, patch
import types
import zipfile

from langchain_core.documents import Document

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app.tools.duckduckgo_search as ddg_module  # noqa: E402
import app.tools.llm_client as llm_module  # noqa: E402
import app.tools.tavily_search as tavily_module  # noqa: E402
import app.tools.vector_store as vs_module  # noqa: E402
import app.tools.wikipedia_search as wiki_module  # noqa: E402
from app.tools.duckduckgo_search import get_duckduckgo_search  # noqa: E402
from app.tools.llm_client import get_llm  # noqa: E402
from app.tools.pdf_loader import (  # noqa: E402
    load_epub,
    process_knowledge_library,
    process_pdf,
    split_documents,
)
from app.tools.tavily_search import get_tavily_search  # noqa: E402
from app.tools.vector_store import (  # noqa: E402
    get_embeddings,
    get_or_create_vectorstore,
    get_retriever,
)
from app.tools.wikipedia_search import get_wikipedia_wrapper  # noqa: E402


def _write_minimal_epub(epub_path, chapter_text="胸痛需要及时评估。"):
    with zipfile.ZipFile(epub_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr(
            "META-INF/container.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
""",
        )
        archive.writestr(
            "OEBPS/content.opf",
            """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>Medical Guide</dc:title>
  </metadata>
  <manifest>
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine>
    <itemref idref="chapter1"/>
  </spine>
</package>
""",
        )
        archive.writestr(
            "OEBPS/chapter1.xhtml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>Chapter 1</h1>
    <p>{chapter_text}</p>
  </body>
</html>
""",
        )


def test_get_llm_no_key():
    llm_module._llm_instance = None
    with patch('app.tools.llm_client.OPENAI_API_KEY', None):
        result = get_llm()
        assert result is None


def test_get_llm_with_key():
    llm_module._llm_instance = None
    with patch('app.tools.llm_client.OPENAI_API_KEY', 'fake-key'):
        fake_module = types.SimpleNamespace(ChatOpenAI=MagicMock(return_value=MagicMock()))
        with patch.dict(sys.modules, {'langchain_openai': fake_module}):
            result = get_llm()
            assert result is not None
    llm_module._llm_instance = None  # reset


def test_get_wikipedia():
    wiki_module._wiki_wrapper = None
    # Patch at the source since WikipediaAPIWrapper is lazily imported inside the function
    with patch('langchain_community.utilities.wikipedia.WikipediaAPIWrapper') as mock_wiki:
        mock_wiki.return_value = MagicMock()
        wrapper = get_wikipedia_wrapper()
        assert wrapper is not None
        # Singleton check
        assert get_wikipedia_wrapper() == wrapper
    wiki_module._wiki_wrapper = None  # reset


def test_get_tavily_no_key():
    tavily_module._tavily_search = None
    with patch('app.tools.tavily_search.TAVILY_API_KEY', None):
        result = get_tavily_search()
        assert result is None


def test_get_tavily_with_key():
    tavily_module._tavily_search = None
    with patch('app.tools.tavily_search.TAVILY_API_KEY', 'fake-key'):
        # Patch at the source since TavilySearchResults is lazily imported inside the function
        with patch('langchain_community.tools.tavily_search.TavilySearchResults') as mock_tav:
            mock_tav.return_value = MagicMock()
            result = get_tavily_search()
            assert result is not None
    tavily_module._tavily_search = None  # reset


def test_pdf_loader():
    # Patch at the source since PyPDFLoader is lazily imported inside the function
    with patch('langchain_community.document_loaders.PyPDFLoader') as mock_loader_cls:
        mock_loader = MagicMock()
        mock_loader.load.return_value = []
        mock_loader_cls.return_value = mock_loader

        with patch('app.tools.pdf_loader.split_documents') as mock_split:
            mock_split.return_value = ["chunk1"]
            res = process_pdf("path.pdf")
            assert res == ["chunk1"]


def test_epub_loader(tmp_path):
    epub_path = tmp_path / "medical_book.epub"
    _write_minimal_epub(epub_path, "Chest pain requires urgent evaluation.")

    docs = load_epub(str(epub_path))

    assert len(docs) == 1
    assert "Chest pain requires urgent evaluation." in docs[0].page_content
    assert docs[0].metadata["source"] == str(epub_path)
    assert docs[0].metadata["section"] == "OEBPS/chapter1.xhtml"


def test_process_knowledge_library_empty(tmp_path):
    assert process_knowledge_library(str(tmp_path)) == []


def test_process_knowledge_library_supports_pdf_and_epub(tmp_path):
    department_dir = tmp_path / "cardiology_心内科"
    department_dir.mkdir()
    (department_dir / "guide.pdf").touch()
    (department_dir / "guide.epub").touch()

    def fake_process_document(document_path, metadata=None):
        suffix = os.path.splitext(document_path)[1].lstrip(".").lower()
        return [
            Document(
                page_content=f"{suffix} chunk",
                metadata=dict(metadata or {}),
            )
        ]

    with patch(
        "app.tools.pdf_loader.process_document_with_metadata",
        side_effect=fake_process_document,
    ) as mock_process:
        docs = process_knowledge_library(str(tmp_path))

    assert mock_process.call_count == 2
    assert len(docs) == 2
    assert sorted(doc.metadata["source_type"] for doc in docs) == ["epub", "pdf"]
    assert {doc.metadata["department"] for doc in docs} == {"cardiology"}


def test_get_duckduckgo_no_import():
    ddg_module._ddg_search = None
    # Patch the actual source to trigger ImportError in the local import
    with patch('langchain_community.tools.DuckDuckGoSearchRun', side_effect=ImportError):
        # We need to be careful with __import__ patching
        with patch('app.tools.duckduckgo_search.logger') as mock_log:
            res = get_duckduckgo_search()
            assert res is None
            mock_log.warning.assert_called()


def test_get_duckduckgo_success():
    ddg_module._ddg_search = None
    with patch('langchain_community.tools.DuckDuckGoSearchRun') as mock_ddg:
        mock_ddg.return_value = MagicMock()
        res = get_duckduckgo_search()
        assert res is not None
    ddg_module._ddg_search = None


def test_vector_store_embeddings():
    vs_module._embeddings = None
    with patch('langchain_huggingface.embeddings.HuggingFaceEmbeddings') as mock_emb:
        mock_emb.return_value = MagicMock()
        res = get_embeddings()
        assert res is not None
    vs_module._embeddings = None


def test_vector_store_get_or_create():
    vs_module._vectorstore = None
    vs_module._embeddings = MagicMock()

    with patch('langchain_community.vectorstores.Chroma') as mock_chroma_cls:
        mock_vs = MagicMock()
        mock_vs._collection.count.return_value = 5
        mock_chroma_cls.return_value = mock_vs

        # Test loading existing
        with patch('os.path.exists', return_value=True):
            with patch('os.listdir', return_value=['chroma.sqlite3']):
                res = get_or_create_vectorstore(persist_dir="fake")
                assert res is not None

        vs_module._vectorstore = None
        # Test creation from docs
        with patch('os.path.exists', return_value=False):
            with patch('os.makedirs'):
                res = get_or_create_vectorstore(documents=[MagicMock()], persist_dir="new")
                assert res is not None

    vs_module._vectorstore = None


def test_get_retriever():
    vs_module._vectorstore = MagicMock()
    vs_module._vectorstore.as_retriever.return_value = MagicMock()
    res = get_retriever()
    assert res is not None

    vs_module._vectorstore = None
    with patch('app.tools.vector_store.get_or_create_vectorstore', return_value=None):
        assert get_retriever() is None


def test_split_documents():
    mock_doc = MagicMock()
    with patch('langchain_text_splitters.RecursiveCharacterTextSplitter') as mock_splitter_cls:
        mock_splitter = MagicMock()
        mock_splitter.split_documents.return_value = [mock_doc]
        mock_splitter_cls.from_tiktoken_encoder.return_value = mock_splitter

        res = split_documents([mock_doc])
        assert len(res) == 1
