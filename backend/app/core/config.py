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

# ── API Keys ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen3.5-plus")
LIGHT_LLM_MODEL = os.getenv("LIGHT_LLM_MODEL", "qwen3.5-flash")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
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

DEPARTMENT_HINT_FOLDERS = {
    code: department_folder_name(code)
    for code in list_department_codes()
}
