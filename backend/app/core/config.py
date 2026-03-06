"""
MediGenius — core/config.py
Environment variables and path constants.
"""

import os

from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}

# ── Paths ──────────────────────────────────────────────────────────────────────
# backend/app/core/config.py -> backend/
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Ensure logs and storage are inside backend directory
LOG_DIR = os.getenv("LOG_DIR", os.path.join(_BACKEND_DIR, "logs"))
CHAT_DB_PATH = os.getenv("CHAT_DB_PATH", os.path.join(_BACKEND_DIR, "storage", "chat_db", "medigenius.db"))
VECTOR_STORE_DIR = os.getenv("VECTOR_STORE_DIR", os.path.join(_BACKEND_DIR, "storage", "vector_store"))
PDF_PATH = os.getenv("PDF_PATH", os.path.join(_BACKEND_DIR, "data", "medical_book.pdf"))
PROFILE_STORE_DIR = os.getenv("PROFILE_STORE_DIR", os.path.join(_BACKEND_DIR, "storage", "profiles"))
EMBEDDING_MODEL_NAME = os.getenv(
    "EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2"
)
RAG_ENABLED = _env_bool("RAG_ENABLED", True)

# ── API Keys ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")
LIGHT_LLM_MODEL = os.getenv("LIGHT_LLM_MODEL", LLM_MODEL)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
