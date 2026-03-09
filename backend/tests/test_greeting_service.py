"""Tests for proactive welcome-message generation."""

from unittest.mock import patch

from app.services.database_service import db_service
from app.services.greeting_service import WELCOME_SOURCE, GreetingService


def test_generate_greeting_uses_profile_ecg_context():
    service = GreetingService()

    with patch.object(db_service, "get_chat_history", return_value=[]), \
         patch.object(db_service, "save_message") as mock_save, \
         patch("app.services.greeting_service.load_profile") as mock_profile, \
         patch("app.services.greeting_service.get_light_llm", return_value=None), \
         patch("app.services.greeting_service._fetch_weather", return_value=""):
        mock_profile.return_value = {
            "basic_info": {},
            "preferences": {"language": "zh-CN"},
            "current_context": {
                "last_ecg_diagnosis": "窦性心律",
                "last_ecg_risk_level": "low",
                "last_ecg_heart_rate": "72 bpm",
            },
        }

        result = service.generate_greeting("sess-1", timezone_name="Asia/Shanghai")

    assert result["success"] is True
    assert result["source"] == WELCOME_SOURCE
    assert "ecg" in result["context_used"]
    mock_save.assert_called_once()
    saved_message = mock_save.call_args.args[2]
    assert "心电" in saved_message


def test_generate_greeting_reuses_existing_welcome():
    service = GreetingService()
    existing = [{
        "role": "assistant",
        "content": "欢迎回来",
        "source": WELCOME_SOURCE,
    }]

    with patch.object(db_service, "get_chat_history", return_value=existing), \
         patch.object(db_service, "save_message") as mock_save:
        result = service.generate_greeting("sess-2")

    assert result["success"] is True
    assert result["created"] is False
    assert result["response"] == "欢迎回来"
    mock_save.assert_not_called()
