"""
MediGenius — core/config.py
Environment variables and path constants.
"""

import os

from dotenv import load_dotenv

from app.core.medical_taxonomy import department_folder_name, list_department_codes

load_dotenv()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw.strip())
    except Exception:
        return default

# ── Paths ──────────────────────────────────────────────────────────────────────
# backend/app/core/config.py -> backend/
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Ensure logs and storage are inside backend directory
LOG_DIR = os.getenv("LOG_DIR", os.path.join(_BACKEND_DIR, "logs"))
CHAT_DB_PATH = os.getenv("CHAT_DB_PATH", os.path.join(_BACKEND_DIR, "storage", "chat_db", "medigenius.db"))
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", os.path.join(_BACKEND_DIR, "storage", "vector_store"))
PDF_PATH = os.getenv("PDF_PATH", os.path.join(_BACKEND_DIR, "data", "medical_book.pdf"))
KNOWLEDGE_ROOT_DIR = os.getenv(
    "KNOWLEDGE_ROOT_DIR",
    os.path.join(_BACKEND_DIR, "data", "knowledge"),
)
DEPARTMENT_KNOWLEDGE_DIR = os.getenv(
    "DEPARTMENT_KNOWLEDGE_DIR",
    os.path.join(KNOWLEDGE_ROOT_DIR, "departments"),
)
GENERAL_MEDICAL_KNOWLEDGE_DIR = os.getenv(
    "GENERAL_MEDICAL_KNOWLEDGE_DIR",
    os.path.join(KNOWLEDGE_ROOT_DIR, "medical", department_folder_name("general_medical")),
)
PROFILE_STORE_DIR = os.getenv("PROFILE_STORE_DIR", os.path.join(_BACKEND_DIR, "storage", "profiles"))
ECG_REPORT_PDF_DIR = os.getenv(
    "ECG_REPORT_PDF_DIR",
    os.path.join(_BACKEND_DIR, "storage", "ecg_reports"),
)
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)
RAG_ENABLED = _env_bool("RAG_ENABLED", True)
WEB_SEARCH_ENABLED = _env_bool("WEB_SEARCH_ENABLED", True)
WEB_SEARCH_USE_LLM_DECIDER = _env_bool("WEB_SEARCH_USE_LLM_DECIDER", False)
QUERY_REWRITER_ENABLED = _env_bool("QUERY_REWRITER_ENABLED", True)
QUERY_REWRITER_USE_LLM = _env_bool("QUERY_REWRITER_USE_LLM", True)
QUERY_REWRITER_MAX_SUBQUERIES = _env_int("QUERY_REWRITER_MAX_SUBQUERIES", 3)
HYBRID_RETRIEVAL_ENABLED = _env_bool("HYBRID_RETRIEVAL_ENABLED", True)
HYBRID_VECTOR_TOPK_SIMPLE = _env_int("HYBRID_VECTOR_TOPK_SIMPLE", 3)
HYBRID_VECTOR_TOPK_COMPLEX = _env_int("HYBRID_VECTOR_TOPK_COMPLEX", 5)
HYBRID_KEYWORD_TOPK_SIMPLE = _env_int("HYBRID_KEYWORD_TOPK_SIMPLE", 2)
HYBRID_KEYWORD_TOPK_COMPLEX = _env_int("HYBRID_KEYWORD_TOPK_COMPLEX", 4)
HYBRID_RETRIEVAL_MAX_CONTEXT = _env_int("HYBRID_RETRIEVAL_MAX_CONTEXT", 24)
RAG_CHUNK_STRATEGY = os.getenv("RAG_CHUNK_STRATEGY", "adaptive")
RAG_CHUNK_SIZE = _env_int("RAG_CHUNK_SIZE", 512)
RAG_CHUNK_OVERLAP = _env_int("RAG_CHUNK_OVERLAP", 128)
RAG_PARENT_CHILD_ENABLED = _env_bool("RAG_PARENT_CHILD_ENABLED", True)
RAG_PARENT_CHUNK_SIZE = _env_int("RAG_PARENT_CHUNK_SIZE", 1600)
RAG_PARENT_CHUNK_OVERLAP = _env_int("RAG_PARENT_CHUNK_OVERLAP", 160)
RAG_CHILD_CHUNK_SIZE = _env_int("RAG_CHILD_CHUNK_SIZE", 480)
RAG_CHILD_CHUNK_OVERLAP = _env_int("RAG_CHILD_CHUNK_OVERLAP", 120)
RERANKER_MODEL_ENABLED = _env_bool("RERANKER_MODEL_ENABLED", False)
RERANKER_MODEL_NAME = os.getenv("RERANKER_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
RERANKER_STAGE1_TOP_N = _env_int("RERANKER_STAGE1_TOP_N", 12)
RERANKER_FINAL_TOP_K = _env_int("RERANKER_FINAL_TOP_K", 6)
RERANKER_RULE_WEIGHT = _env_float("RERANKER_RULE_WEIGHT", 0.45)
RERANKER_MODEL_WEIGHT = _env_float("RERANKER_MODEL_WEIGHT", 0.55)
GENERATION_MAX_CONTEXT_CHUNKS = _env_int("GENERATION_MAX_CONTEXT_CHUNKS", 6)
GENERATION_MAX_CONTEXT_CHARS = _env_int("GENERATION_MAX_CONTEXT_CHARS", 5200)
GENERATION_REQUIRE_CITATION = _env_bool("GENERATION_REQUIRE_CITATION", True)

# ── API Keys ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
OPENAI_WIRE_API = os.getenv("OPENAI_WIRE_API", "chat").strip().lower()
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-plus")
LIGHT_LLM_MODEL = os.getenv("LIGHT_LLM_MODEL", "qwen3.5-flash")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
LANGSMITH_TRACING = _env_bool("LANGSMITH_TRACING", False)
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "medigenius")
LANGSMITH_ENDPOINT = os.getenv("LANGSMITH_ENDPOINT")
LANGSMITH_WORKSPACE_ID = os.getenv("LANGSMITH_WORKSPACE_ID")
LANGSMITH_TAGS = os.getenv("LANGSMITH_TAGS", "medigenius,backend")
MODEL_ROUTING_CONFIG_PATH = os.getenv(
    "MODEL_ROUTING_CONFIG_PATH",
    os.path.join(_BACKEND_DIR, "storage", "model_routing.json"),
)

# ── ECG Remote Monitor ────────────────────────────────────────────────────────
ECG_SITE_URL = os.getenv(
    "ECG_SITE_URL",
    "http://124.220.204.12:8080/index#/system/doctor",
)
ECG_SITE_USER = os.getenv("ECG_SITE_USER", "doctor")
ECG_SITE_PASS = os.getenv("ECG_SITE_PASS", "123456")
ECG_MONITOR_TARGET_CREATE_TIME = os.getenv(
    "ECG_MONITOR_TARGET_CREATE_TIME",
    "2026-01-17 13:46:03",
)
ECG_MONITOR_DATA_MODE = os.getenv("ECG_MONITOR_DATA_MODE", "synthetic_normal")

DEPARTMENT_HINT_FOLDERS = {
    code: department_folder_name(code)
    for code in list_department_codes()
}
