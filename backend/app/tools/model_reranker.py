"""
MediGenius — tools/model_reranker.py
Optional cross-encoder reranker with graceful fallback.
"""

from __future__ import annotations

import threading
from typing import List, Optional

from app.core.config import RERANKER_MODEL_ENABLED, RERANKER_MODEL_NAME
from app.core.logging_config import logger

_model = None
_lock = threading.Lock()
_model_failed = False


def get_model_reranker():
    """Return cached CrossEncoder reranker, or None when disabled/unavailable."""
    global _model, _model_failed
    if not RERANKER_MODEL_ENABLED:
        return None
    if _model_failed:
        return None
    if _model is not None:
        return _model

    with _lock:
        if _model is not None:
            return _model
        if _model_failed:
            return None
        try:
            from sentence_transformers import CrossEncoder

            _model = CrossEncoder(RERANKER_MODEL_NAME, device="cpu")
            logger.info("Reranker model loaded: %s", RERANKER_MODEL_NAME)
        except Exception as exc:
            _model_failed = True
            logger.warning("Reranker model unavailable (%s): %s", RERANKER_MODEL_NAME, exc)
            return None
    return _model


def rerank_with_model(query: str, passages: List[str]) -> Optional[List[float]]:
    model = get_model_reranker()
    if model is None:
        return None
    if not query.strip() or not passages:
        return None
    try:
        pairs = [[query, text] for text in passages]
        scores = model.predict(pairs)
        return [float(item) for item in scores]
    except Exception as exc:
        logger.warning("Model reranker failed, fallback to rule stage: %s", exc)
        return None

