"""
MediGenius — tools/llm_client.py
Groq LLM client singleton.
"""

from app.core.config import OPENAI_API_KEY, OPENAI_BASE_URL
from app.core.logging_config import logger

_llm_instance = None


def get_llm():
    """Return a cached ChatOpenAI LLM instance, or None if API key is missing."""
    global _llm_instance
    if _llm_instance is None:
        if not OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not found in environment variables")
            return None
        from langchain_openai import ChatOpenAI

        _llm_instance = ChatOpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
            model_name="qwen3.5-plus",
            temperature=0.3,
            max_tokens=2048,
        )
        logger.info("LLM client initialized (OpenAI Compatible / qwen3.5-plus)")
    return _llm_instance
