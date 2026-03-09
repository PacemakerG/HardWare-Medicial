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
            "preferred_name": "小林",
            "detail_level": "detailed",
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
    assert normalized["preferences"]["preferred_name"] == "小林"
    assert normalized["preferences"]["detail_level"] == "detailed"
    assert normalized["current_context"]["last_ecg_risk_level"] == "medium"
    assert "unexpected_section" not in normalized


def test_update_profile_persists_schema_constrained_data(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "PROFILE_STORE_DIR", str(tmp_path))
    session_id = "session-profile-test"

    ps.update_profile(
        session_id,
        {
            "basic_info": {"age": "34", "gender": "female", "foo": "bar"},
            "preferences": {"language": "zh-CN", "preferred_name": "王女士", "detail_level": "brief"},
            "current_context": {"symptom": "咳嗽", "last_ecg_diagnosis": "窦性心律"},
        },
    )

    profile = ps.load_profile(session_id)
    assert profile["basic_info"]["age"] == 34
    assert profile["basic_info"]["gender"] == "female"
    assert "foo" not in profile["basic_info"]
    assert profile["preferences"]["language"] == "zh-CN"
    assert profile["preferences"]["preferred_name"] == "王女士"
    assert profile["preferences"]["detail_level"] == "brief"
    assert profile["current_context"]["symptom"] == "咳嗽"
    assert profile["current_context"]["last_ecg_diagnosis"] == "窦性心律"

    expected_file = os.path.join(str(tmp_path), "default__anonymous.json")
    assert os.path.exists(expected_file)


def test_profile_scoped_by_user_not_session(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "PROFILE_STORE_DIR", str(tmp_path))

    ps.update_profile(
        "session-a",
        {"current_context": {"symptom": "胸闷"}},
        tenant_id="tenant-1",
        user_id="user-1",
    )

    # Same tenant+user, different session should share long-term profile.
    profile_same_user = ps.load_profile(
        "session-b",
        tenant_id="tenant-1",
        user_id="user-1",
    )
    assert profile_same_user["current_context"]["symptom"] == "胸闷"

    # Different user should be isolated.
    profile_other_user = ps.load_profile(
        "session-c",
        tenant_id="tenant-1",
        user_id="user-2",
    )
    assert profile_other_user["current_context"] == {}
