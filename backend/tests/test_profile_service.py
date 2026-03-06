"""Tests for profile schema normalization and persistence."""

import os

from app.services import profile_service as ps


def test_normalize_profile_updates_filters_and_coerces():
    updates = {
        "basic_info": {
            "age": "29",
            "gender": "MALE",
            "height_cm": 175.8,
            "unknown_field": "ignored",
        },
        "preferences": {
            "language": "中文",
            "communication_style": "warm",
        },
        "current_context": {
            "symptom": "头痛",
            "medication": "ibuprofen",
            "last_checkup": "2025-12-01",
            "last_ecg_risk_level": "medium",
        },
        "unexpected_section": {"foo": "bar"},
    }

    normalized = ps._normalize_profile_updates(updates)

    assert normalized["basic_info"]["age"] == 29
    assert normalized["basic_info"]["gender"] == "male"
    assert normalized["basic_info"]["height_cm"] == 175
    assert "unknown_field" not in normalized["basic_info"]
    assert normalized["preferences"]["language"] == "中文"
    assert normalized["current_context"]["last_ecg_risk_level"] == "medium"
    assert "unexpected_section" not in normalized


def test_update_profile_persists_schema_constrained_data(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "PROFILE_STORE_DIR", str(tmp_path))
    session_id = "session-profile-test"

    ps.update_profile(
        session_id,
        {
            "basic_info": {"age": "34", "gender": "female", "foo": "bar"},
            "preferences": {"language": "zh-CN"},
            "current_context": {"symptom": "咳嗽", "last_ecg_diagnosis": "窦性心律"},
        },
    )

    profile = ps.load_profile(session_id)
    assert profile["basic_info"]["age"] == 34
    assert profile["basic_info"]["gender"] == "female"
    assert "foo" not in profile["basic_info"]
    assert profile["preferences"]["language"] == "zh-CN"
    assert profile["current_context"]["symptom"] == "咳嗽"
    assert profile["current_context"]["last_ecg_diagnosis"] == "窦性心律"

    expected_file = os.path.join(str(tmp_path), f"{session_id}.json")
    assert os.path.exists(expected_file)
