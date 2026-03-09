"""
MediGenius — services/profile_service.py
Lightweight user profile storage (JSON) and async profile update helpers.
"""

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any, Dict

from app.core.config import PROFILE_STORE_DIR
from app.core.logging_config import logger
from app.tools.llm_client import get_light_llm

_profile_lock = threading.Lock()

PROFILE_SCHEMA = {
    "basic_info": {
        "age": {"type": "integer", "description": "年龄"},
        "gender": {"type": "string", "enum": ["male", "female", "other"]},
        "height_cm": {"type": "integer"},
        "weight_kg": {"type": "integer"},
    },
    "preferences": {
        "language": {"type": "string", "description": "偏好语言"},
        "preferred_name": {"type": "string", "description": "偏好称呼"},
        "communication_style": {"type": "string"},
        "detail_level": {"type": "string", "enum": ["brief", "balanced", "detailed"]},
    },
    "current_context": {
        "symptom": {"type": "string"},
        "medication": {"type": "string"},
        "last_checkup": {"type": "string"},
        "last_ecg_report_id": {"type": "string"},
        "last_ecg_risk_level": {"type": "string"},
        "last_ecg_diagnosis": {"type": "string"},
        "last_ecg_heart_rate": {"type": "string"},
        "last_ecg_axis_degree": {"type": "string"},
    },
}


def _sanitize_session_id(session_id: str) -> str:
    if not session_id:
        return "anonymous"
    return re.sub(r"[^a-zA-Z0-9_-]", "_", session_id)


def _sanitize_identity(value: str, default: str) -> str:
    if not value:
        return default
    return re.sub(r"[^a-zA-Z0-9_.@:-]", "_", value)


def _profile_path(session_id: str, *, tenant_id: str = "default", user_id: str = "anonymous") -> str:
    del session_id  # profile is scoped by tenant+user, not chat session
    if not os.path.exists(PROFILE_STORE_DIR):
        os.makedirs(PROFILE_STORE_DIR, exist_ok=True)
    safe_tenant = _sanitize_identity(tenant_id, "default")
    safe_user = _sanitize_identity(user_id, "anonymous")
    return os.path.join(PROFILE_STORE_DIR, f"{safe_tenant}__{safe_user}.json")


def _default_profile() -> Dict[str, Any]:
    return {
        "basic_info": {},
        "preferences": {},
        "current_context": {},
        "meta": {
            "version": 1,
            "last_updated": None,
        },
    }


def load_profile(
    session_id: str,
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
) -> Dict[str, Any]:
    """Load a user profile JSON, returning defaults on first use/corruption."""
    path = _profile_path(session_id, tenant_id=tenant_id, user_id=user_id)
    if not os.path.exists(path):
        return _default_profile()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.warning("Profile data malformed for session %s", session_id[:8])
            return _default_profile()
        return data
    except Exception as exc:
        logger.error("Failed to load profile for session %s: %s", session_id[:8], exc)
        return _default_profile()


def _atomic_save_profile(
    session_id: str,
    profile: Dict[str, Any],
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
) -> None:
    path = _profile_path(session_id, tenant_id=tenant_id, user_id=user_id)
    temp_path = f"{path}.tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=True, indent=2)
    os.replace(temp_path, path)


def render_profile_as_text(profile: Dict[str, Any]) -> str:
    """Convert structured profile JSON to compact natural-language context."""
    sections = []

    basic = profile.get("basic_info") or {}
    prefs = profile.get("preferences") or {}
    context = profile.get("current_context") or {}

    if basic:
        sections.append(
            "Basic Info: " + "; ".join(f"{k}: {v}" for k, v in basic.items())
        )
    if prefs:
        sections.append(
            "Preferences: " + "; ".join(f"{k}: {v}" for k, v in prefs.items())
        )
    if context:
        sections.append(
            "Current Context: " + "; ".join(f"{k}: {v}" for k, v in context.items())
        )

    if not sections:
        return "No persistent user profile information recorded yet."

    return "\n".join(sections)


def _merge_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for k, v in updates.items():
        if isinstance(v, str) and not v.strip():
            continue
        merged[k] = v
    return merged


def _coerce_by_rule(value: Any, rule: Dict[str, Any]) -> Any:
    expected_type = rule.get("type")

    if expected_type == "integer":
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(float(text))
            except ValueError:
                return None
        return None

    if expected_type == "string":
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        enum_values = rule.get("enum")
        if enum_values:
            for item in enum_values:
                if text.lower() == str(item).lower():
                    return item
            return None
        return text[:200]

    return None


def _normalize_profile_updates(updates: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Filter unknown fields and coerce values according to PROFILE_SCHEMA."""
    normalized = {section: {} for section in PROFILE_SCHEMA.keys()}

    if not isinstance(updates, dict):
        return normalized

    for section, fields in PROFILE_SCHEMA.items():
        section_updates = updates.get(section) or {}
        if not isinstance(section_updates, dict):
            continue
        for field, rule in fields.items():
            if field not in section_updates:
                continue
            coerced = _coerce_by_rule(section_updates[field], rule)
            if coerced is not None:
                normalized[section][field] = coerced

    return normalized


def update_profile(
    session_id: str,
    updates: Dict[str, Any],
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
) -> Dict[str, Any]:
    """Merge profile updates into persistent JSON profile using atomic writes."""
    normalized_updates = _normalize_profile_updates(updates)
    if not any(normalized_updates.values()):
        return load_profile(session_id, tenant_id=tenant_id, user_id=user_id)

    with _profile_lock:
        profile = load_profile(session_id, tenant_id=tenant_id, user_id=user_id)
        profile["basic_info"] = _merge_dict(
            profile.get("basic_info") or {},
            normalized_updates.get("basic_info") or {},
        )
        profile["preferences"] = _merge_dict(
            profile.get("preferences") or {},
            normalized_updates.get("preferences") or {},
        )
        profile["current_context"] = _merge_dict(
            profile.get("current_context") or {},
            normalized_updates.get("current_context") or {},
        )
        profile["meta"] = {
            **(profile.get("meta") or {}),
            "version": 1,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        _atomic_save_profile(
            session_id,
            profile,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return profile


def _extract_json_block(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return "{}"
    return text[start : end + 1]


def infer_profile_updates(
    question: str,
    answer: str,
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
) -> Dict[str, Any]:
    """
    Infer profile updates via a lightweight model.
    Returns a strict JSON-compatible dict or empty dict.
    """
    llm = get_light_llm(tenant_id=tenant_id, user_id=user_id)
    if not llm:
        return {}

    prompt = (
        "You extract durable user profile facts from a conversation.\n"
        f"Follow this schema exactly: {json.dumps(PROFILE_SCHEMA, ensure_ascii=False)}\n"
        "Return ONLY JSON with keys: basic_info, preferences, current_context.\n"
        "Each key must map to an object. If no durable fact, use empty objects.\n\n"
        f"User Message: {question[:1200]}\n"
        f"Assistant Reply: {answer[:1200]}\n"
    )

    try:
        raw = llm.invoke(prompt)
        content = raw.content if hasattr(raw, "content") else str(raw)
        parsed = json.loads(_extract_json_block(content))
        if not isinstance(parsed, dict):
            return {}
        raw_updates = {
            "basic_info": parsed.get("basic_info") or {},
            "preferences": parsed.get("preferences") or {},
            "current_context": parsed.get("current_context") or {},
        }
        return _normalize_profile_updates(raw_updates)
    except Exception as exc:
        logger.warning("Profile update inference failed: %s", exc)
        return {}


def schedule_profile_update(
    session_id: str,
    question: str,
    answer: str,
    *,
    tenant_id: str = "default",
    user_id: str = "anonymous",
) -> None:
    """Run profile extraction and write in a background daemon thread."""

    def _worker():
        updates = infer_profile_updates(
            question,
            answer,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not updates:
            return
        update_profile(
            session_id,
            updates,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        logger.info(
            "Profile updated asynchronously for tenant=%s user=%s session=%s",
            tenant_id,
            user_id,
            session_id[:8],
        )

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
