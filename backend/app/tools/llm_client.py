"""
MediGenius — tools/llm_client.py
OpenAI-compatible LLM client singleton.
"""

from app.core.config import (
    LIGHT_LLM_MODEL,
    LLM_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from app.core.logging_config import logger

_llm_instance = None
_light_llm_instance = None


def get_llm():
    """Return a cached ChatOpenAI instance for main generation."""
    global _llm_instance
    if _llm_instance is None:
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            return None
        from langchain_openai import ChatOpenAI

        kwargs = {
            "api_key": OPENAI_API_KEY,
            "model": LLM_MODEL,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL

        _llm_instance = ChatOpenAI(**kwargs)
        logger.info("LLM client initialized (OpenAI-compatible / %s)", LLM_MODEL)
    return _llm_instance


def get_light_llm():
    """Return a cached ChatOpenAI instance for lightweight routing/judge tasks."""
    global _light_llm_instance
    if _light_llm_instance is None:
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            return None
        from langchain_openai import ChatOpenAI

        kwargs = {
            "api_key": OPENAI_API_KEY,
            "model": LIGHT_LLM_MODEL,
            "temperature": 0.0,
            "max_tokens": 128,
        }
        if OPENAI_BASE_URL:
            kwargs["base_url"] = OPENAI_BASE_URL

        _light_llm_instance = ChatOpenAI(**kwargs)
        logger.info(
            "Light LLM client initialized (OpenAI-compatible / %s)",
            LIGHT_LLM_MODEL,
        )
    return _light_llm_instance
