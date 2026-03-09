"""
MediGenius — services/greeting_service.py
Generate a proactive welcome message for an empty session.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import httpx

from app.core.logging_config import logger
from app.services.database_service import db_service
from app.services.profile_service import load_profile
from app.tools.llm_client import get_light_llm

WELCOME_SOURCE = "Welcome Concierge"
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"
TRIVIAL_USER_MESSAGES = {
    "hi",
    "hello",
    "hey",
    "你好",
    "您好",
    "嗨",
    "哈喽",
}
RISK_LEVEL_LABELS = {
    "low": "低",
    "medium": "中",
    "high": "高",
}
WEATHER_LABELS = {
    0: "晴朗",
    1: "大致晴",
    2: "少云",
    3: "阴天",
    45: "有雾",
    48: "雾较重",
    51: "毛毛雨",
    53: "小雨",
    55: "中雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "阵雨",
    81: "较强阵雨",
    82: "强阵雨",
    95: "雷暴",
    96: "伴冰雹雷暴",
    99: "强雷暴",
}


def _display_timestamp() -> str:
    return datetime.now().strftime("%I:%M %p")


def _resolve_now(timezone_name: str | None) -> datetime:
    if not timezone_name:
        return datetime.now()
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except Exception:
        logger.info("GreetingService: invalid timezone %s, falling back to server time", timezone_name)
        return datetime.now()


def _day_period(now: datetime) -> str:
    hour = now.hour
    if hour < 11:
        return "早上"
    if hour < 18:
        return "下午"
    return "晚上"


def _shorten(text: str, limit: int = 36) -> str:
    clean = " ".join((text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1] + "..."


def _extract_last_user_topic(history: List[Dict[str, Any]]) -> str:
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        content = (item.get("content") or "").strip()
        if not content or content.lower() in TRIVIAL_USER_MESSAGES:
            continue
        return _shorten(content)
    return ""


def _build_profile_hint(profile: Dict[str, Any]) -> str:
    preferences = profile.get("preferences") or {}
    basic_info = profile.get("basic_info") or {}

    language = (preferences.get("language") or "").strip()
    style = (preferences.get("communication_style") or "").strip()
    age = basic_info.get("age")

    parts: List[str] = []
    if language:
        parts.append(f"我会继续优先用 {language} 和你交流")
    if style:
        parts.append(f"保持 {style} 的沟通方式")
    if age:
        parts.append(f"也会尽量结合你目前记录的年龄信息来组织建议")

    if not parts:
        return ""
    return "，".join(parts) + "。"


def _build_ecg_hint(profile: Dict[str, Any]) -> str:
    context = profile.get("current_context") or {}
    diagnosis = (context.get("last_ecg_diagnosis") or "").strip()
    risk_level = (context.get("last_ecg_risk_level") or "").strip().lower()
    heart_rate = (context.get("last_ecg_heart_rate") or "").strip()

    if not diagnosis and not heart_rate and not risk_level:
        return ""

    parts = []
    if diagnosis:
        parts.append(f"上次留存的心电结论是{diagnosis}")
    if risk_level:
        parts.append(f"风险分层偏{RISK_LEVEL_LABELS.get(risk_level, risk_level)}")
    if heart_rate:
        parts.append(f"记录心率为 {heart_rate}")
    return "，".join(parts) + "。"


def _fetch_weather(latitude: float | None, longitude: float | None, timezone_name: str | None) -> str:
    if latitude is None or longitude is None:
        return ""

    params = {
        "latitude": round(latitude, 4),
        "longitude": round(longitude, 4),
        "current": "temperature_2m,apparent_temperature,weather_code",
        "timezone": timezone_name or "auto",
    }

    try:
        with httpx.Client(timeout=2.5) as client:
            response = client.get(WEATHER_API_URL, params=params)
            response.raise_for_status()
        payload = response.json()
        current = payload.get("current") or {}
        temperature = current.get("temperature_2m")
        apparent_temperature = current.get("apparent_temperature")
        weather_code = current.get("weather_code")

        if temperature is None and apparent_temperature is None and weather_code is None:
            return ""

        weather_label = WEATHER_LABELS.get(weather_code, "天气平稳")
        temp_label = f"{round(float(temperature))}°C" if temperature is not None else ""
        feel_label = (
            f"，体感约 {round(float(apparent_temperature))}°C"
            if apparent_temperature is not None
            else ""
        )
        temp_part = f"，气温约 {temp_label}" if temp_label else ""
        return f"你那边现在大概是{weather_label}{temp_part}{feel_label}。"
    except Exception as exc:
        logger.info("GreetingService: weather lookup skipped: %s", exc)
        return ""


def _looks_chinese(text: str) -> bool:
    chinese_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    return chinese_count >= 8


def _render_with_llm(context: Dict[str, str], context_used: List[str], day_period: str) -> str:
    llm = get_light_llm()
    if not llm:
        return ""

    prompt = (
        "你是 MediGenius 的首屏欢迎助手。\n"
        "请根据已知上下文，主动发起一句自然的中文问候，并补上一句具体追问。\n"
        "要求：\n"
        "1. 只使用已提供的事实，不要编造用户情况\n"
        "2. 全文 2 到 3 句，简洁、有温度、像私人健康助理\n"
        "3. 可以优先融合天气、上次对话、用户画像、ECG 摘要中的 1 到 2 项\n"
        "4. 不要做诊断，不要给过重的风险结论，不要使用 markdown\n\n"
        f"当前时段：{day_period}\n"
        f"启用上下文：{', '.join(context_used) or 'time'}\n"
        f"天气：{context.get('weather') or '无'}\n"
        f"上次对话：{context.get('history') or '无'}\n"
        f"用户画像：{context.get('profile') or '无'}\n"
        f"ECG 摘要：{context.get('ecg') or '无'}\n"
    )

    try:
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        text = " ".join((text or "").split())
        if not text or not _looks_chinese(text):
            return ""
        return text
    except Exception as exc:
        logger.info("GreetingService: llm greeting skipped: %s", exc)
        return ""


def _fallback_greeting(context: Dict[str, str], context_used: List[str], day_period: str) -> str:
    opening = f"{day_period}好，我是 MediGenius。"
    details: List[str] = []

    if "history" in context_used and context.get("history"):
        details.append(f"上次我们聊到“{context['history']}”。")
    if "ecg" in context_used and context.get("ecg"):
        details.append(context["ecg"])
    if "weather" in context_used and context.get("weather"):
        details.append(context["weather"])
    if "profile" in context_used and context.get("profile"):
        details.append(context["profile"])

    if not details:
        details.append("你可以直接告诉我今天的症状、生活方式困扰，或者上传 ECG 参数让我一起看。")

    if "history" in context_used and context.get("history"):
        question = "那个情况今天有变化吗，还是你想先补充新的不适？"
    elif "ecg" in context_used and context.get("ecg"):
        question = "你今天想继续跟进心电变化，还是先说说现在有没有胸闷、心悸或睡眠问题？"
    elif "weather" in context_used and context.get("weather"):
        question = "你今天想先聊气温变化带来的不舒服，还是直接说说当前症状？"
    else:
        question = "你今天想先聊症状、用药，还是让我帮你解读一份 ECG 数据？"

    return " ".join([opening, *details[:2], question])


def _find_existing_welcome(history: List[Dict[str, Any]]) -> Dict[str, Any] | None:
    if len(history) != 1:
        return None
    message = history[0]
    if message.get("role") != "assistant":
        return None
    if (message.get("source") or "") != WELCOME_SOURCE:
        return None
    return message


class GreetingService:
    """Generate or reuse a welcome message for the current empty session."""

    def generate_greeting(
        self,
        session_id: str,
        *,
        latitude: float | None = None,
        longitude: float | None = None,
        timezone_name: str | None = None,
        locale: str | None = None,
    ) -> Dict[str, Any]:
        history = db_service.get_chat_history(session_id)
        existing = _find_existing_welcome(history)
        if existing:
            return {
                "response": existing.get("content") or "",
                "source": existing.get("source") or WELCOME_SOURCE,
                "timestamp": _display_timestamp(),
                "success": True,
                "session_id": session_id,
                "created": False,
                "context_used": ["time"],
            }
        if history:
            return {
                "response": "",
                "source": WELCOME_SOURCE,
                "timestamp": _display_timestamp(),
                "success": False,
                "session_id": session_id,
                "created": False,
                "context_used": ["history"],
            }

        now = _resolve_now(timezone_name)
        day_period = _day_period(now)
        profile = load_profile(session_id)
        weather_hint = _fetch_weather(latitude, longitude, timezone_name)
        history_hint = _extract_last_user_topic(history)
        profile_hint = _build_profile_hint(profile)
        ecg_hint = _build_ecg_hint(profile)

        context = {
            "weather": weather_hint,
            "history": history_hint,
            "profile": profile_hint,
            "ecg": ecg_hint,
            "locale": locale or "",
        }
        context_used = [
            name
            for name in ("history", "ecg", "weather", "profile")
            if context.get(name)
        ]

        greeting = _render_with_llm(context, context_used, day_period)
        if not greeting:
            greeting = _fallback_greeting(context, context_used, day_period)

        db_service.save_message(session_id, "assistant", greeting, WELCOME_SOURCE)
        return {
            "response": greeting,
            "source": WELCOME_SOURCE,
            "timestamp": _display_timestamp(),
            "success": True,
            "session_id": session_id,
            "created": True,
            "context_used": context_used or ["time"],
        }


greeting_service = GreetingService()
