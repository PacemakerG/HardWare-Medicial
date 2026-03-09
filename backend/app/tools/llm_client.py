"""
MediGenius — tools/llm_client.py
OpenAI-compatible LLM client singleton.
"""

import json
import os
import threading
from typing import Any, Dict

from app.core.config import (
    LIGHT_LLM_MODEL,
    LLM_MODEL,
    MODEL_ROUTING_CONFIG_PATH,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
)
from app.core.logging_config import logger

_llm_instance = None
_light_llm_instance = None
_llm_instances: Dict[tuple, Any] = {}
_light_llm_instances: Dict[tuple, Any] = {}
_instances_lock = threading.Lock()
_routing_cache: Dict[str, Any] = {"mtime": None, "data": {}}
_routing_lock = threading.Lock()


def _load_routing_config() -> Dict[str, Any]:
    path = MODEL_ROUTING_CONFIG_PATH
    if not path or not os.path.exists(path):
        with _routing_lock:
            _routing_cache["mtime"] = None
            _routing_cache["data"] = {}
        return {}

    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return {}

    with _routing_lock:
        if _routing_cache.get("mtime") == mtime:
            cached = _routing_cache.get("data")
            return cached if isinstance(cached, dict) else {}

        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                loaded = {}
            _routing_cache["mtime"] = mtime
            _routing_cache["data"] = loaded
            logger.info("LLM routing config reloaded from %s", path)
            return loaded
        except Exception as exc:
            logger.warning("Failed to read LLM routing config (%s): %s", path, exc)
            _routing_cache["mtime"] = mtime
            _routing_cache["data"] = {}
            return {}


def _merge_non_empty(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for k, v in (patch or {}).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v
    return merged


def _normalize_routing_block(block: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(block, dict):
        return {}
    return {
        "api_key": block.get("api_key"),
        "base_url": block.get("base_url"),
        "model": block.get("model") or block.get("llm_model"),
        "light_model": block.get("light_model") or block.get("light_llm_model"),
    }


def _resolve_llm_config(tenant_id: str, user_id: str) -> Dict[str, Any]:
    resolved = {
        "api_key": OPENAI_API_KEY,
        "base_url": OPENAI_BASE_URL,
        "model": LLM_MODEL,
        "light_model": LIGHT_LLM_MODEL,
    }
    routing = _load_routing_config()
    if not routing:
        return resolved

    resolved = _merge_non_empty(
        resolved,
        _normalize_routing_block(routing.get("default") or {}),
    )

    tenant_cfg = ((routing.get("tenants") or {}).get(tenant_id) or {})
    resolved = _merge_non_empty(resolved, _normalize_routing_block(tenant_cfg))

    user_cfg = ((tenant_cfg.get("users") or {}).get(user_id) or {})
    resolved = _merge_non_empty(resolved, _normalize_routing_block(user_cfg))
    return resolved


def get_llm(*, tenant_id: str = "default", user_id: str = "anonymous"):
    """Return a cached ChatOpenAI instance for main generation (tenant/user isolated)."""
    global _llm_instance
    cfg = _resolve_llm_config(tenant_id, user_id)
    api_key = cfg.get("api_key")
    model = cfg.get("model") or LLM_MODEL
    base_url = cfg.get("base_url")

    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables")
        return None

    cache_key = ("main", tenant_id, user_id, model, base_url, api_key)
    with _instances_lock:
        cached = _llm_instances.get(cache_key)
        if cached is not None:
            if tenant_id == "default" and user_id == "anonymous":
                _llm_instance = cached
            return cached

        from langchain_openai import ChatOpenAI
        kwargs = {
            "api_key": api_key,
            "model": model,
            "temperature": 0.3,
            "max_tokens": 2048,
        }
        if base_url:
            kwargs["base_url"] = base_url

        instance = ChatOpenAI(**kwargs)
        _llm_instances[cache_key] = instance
        if tenant_id == "default" and user_id == "anonymous":
            _llm_instance = instance
        logger.info(
            "LLM client initialized (tenant=%s user=%s / %s)",
            tenant_id,
            user_id,
            model,
        )
        return instance


def get_light_llm(*, tenant_id: str = "default", user_id: str = "anonymous"):
    """Return cached lightweight LLM instance (tenant/user isolated)."""
    global _light_llm_instance
    cfg = _resolve_llm_config(tenant_id, user_id)
    api_key = cfg.get("api_key")
    model = cfg.get("light_model") or cfg.get("model") or LIGHT_LLM_MODEL
    base_url = cfg.get("base_url")

    if not api_key:
        logger.warning("OPENAI_API_KEY not found in environment variables")
        return None

    cache_key = ("light", tenant_id, user_id, model, base_url, api_key)
    with _instances_lock:
        cached = _light_llm_instances.get(cache_key)
        if cached is not None:
            if tenant_id == "default" and user_id == "anonymous":
                _light_llm_instance = cached
            return cached

        from langchain_openai import ChatOpenAI
        kwargs = {
            "api_key": api_key,
            "model": model,
            "temperature": 0.0,
            "max_tokens": 128,
        }
        if base_url:
            kwargs["base_url"] = base_url

        instance = ChatOpenAI(**kwargs)
        _light_llm_instances[cache_key] = instance
        if tenant_id == "default" and user_id == "anonymous":
            _light_llm_instance = instance
        logger.info(
            "Light LLM client initialized (tenant=%s user=%s / %s)",
            tenant_id,
            user_id,
            model,
        )
        return instance
