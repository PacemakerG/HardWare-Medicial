"""
MediGenius — services/context_compaction_service.py
Synchronous conversation compaction with traceable medical-fact protection.
"""

import json
import re
from typing import Any, Dict, List, Optional

from app.core.config import (
    CONTEXT_COMPRESSION_ENABLED,
    CONTEXT_KEEP_RECENT_MESSAGES,
    CONTEXT_KEEP_RECENT_TOKENS,
    CONTEXT_MAX_MESSAGES,
    CONTEXT_MAX_TOKENS,
)
from app.core.logging_config import logger
from app.core.state import estimate_text_tokens
from app.services.database_service import db_service
from app.tools.llm_client import coerce_response_text, get_llm

_token_encoder = None

_NEGATION_TERMS = ("没有", "无", "否认", "从未", "未见", "未曾", "不曾", "not", "no ")
_FACT_RULES = (
    ("allergy", ("过敏", "allergy", "allergic")),
    ("medication", ("服用", "用药", "药物", "剂量", "mg", " ml", "片", "胰岛素")),
    (
        "test_result",
        (
            "检查",
            "化验",
            "血压",
            "血糖",
            "心率",
            "体温",
            "bpm",
            "mmhg",
            "mmol/l",
            "℃",
        ),
    ),
    ("symptom", ("症状", "疼痛", "发热", "咳嗽", "头晕", "胸闷", "心悸", "呼吸困难")),
)
_ALLOWED_CATEGORIES = {rule[0] for rule in _FACT_RULES} | {"negation"}
_ALLOWED_STATUSES = {"present", "absent", "uncertain"}
_UNIT_PATTERN = re.compile(
    r"(?:\b(?:mg|mcg|ug|g|kg|ml|l|mmhg|mmol/l|mol/l|bpm)\b|μg|次/分|℃|°c|%|片|粒)",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


def _count_tokens(text: str) -> int:
    global _token_encoder
    normalized = text or ""
    if not normalized:
        return 0
    try:
        if _token_encoder is None:
            import tiktoken

            _token_encoder = tiktoken.get_encoding("cl100k_base")
        return len(_token_encoder.encode(normalized))
    except Exception:
        return estimate_text_tokens(normalized)


def _message_text(message: Dict[str, Any]) -> str:
    return f"{message.get('role', '')}: {message.get('content', '')}"


def _messages_tokens(messages: List[Dict[str, Any]]) -> int:
    return sum(_count_tokens(_message_text(item)) for item in messages)


def _extract_json_block(text: str) -> str:
    normalized = (text or "").strip()
    if normalized.startswith("```"):
        normalized = re.sub(r"^```(?:json)?\s*", "", normalized)
        normalized = re.sub(r"\s*```$", "", normalized)
    start = normalized.find("{")
    end = normalized.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("compression response did not contain a JSON object")
    return normalized[start : end + 1]


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _contains_negation(text: str) -> bool:
    lowered = f" {_normalize_space(text).lower()} "
    return any(term in lowered for term in _NEGATION_TERMS)


def _fact_category(text: str) -> Optional[str]:
    lowered = text.lower()
    for category, keywords in _FACT_RULES:
        if any(keyword in lowered for keyword in keywords):
            return category
    if _contains_negation(text):
        return "negation"
    return None


def _validate_fact(
    raw_fact: Dict[str, Any],
    source_messages: Dict[int, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_fact, dict):
        return None
    try:
        source_message_id = int(raw_fact.get("source_message_id"))
    except (TypeError, ValueError):
        return None

    source = source_messages.get(source_message_id)
    category = str(raw_fact.get("category") or "").strip().lower()
    status = str(raw_fact.get("status") or "uncertain").strip().lower()
    statement = _normalize_space(raw_fact.get("statement"))
    source_quote = _normalize_space(raw_fact.get("source_quote"))
    source_content = _normalize_space((source or {}).get("content"))
    if (
        source is None
        or category not in _ALLOWED_CATEGORIES
        or status not in _ALLOWED_STATUSES
        or not statement
        or not source_quote
        or source_quote not in source_content
    ):
        return None

    if any(number not in source_quote for number in _NUMBER_PATTERN.findall(statement)):
        return None
    quote_lower = source_quote.lower()
    if any(
        unit.lower() not in quote_lower for unit in _UNIT_PATTERN.findall(statement)
    ):
        return None
    if (status == "absent" or category == "negation") and not _contains_negation(
        source_quote
    ):
        return None

    observed_at = str(source.get("timestamp") or "").strip()
    return {
        "category": category,
        "statement": statement,
        "status": status,
        "source_message_id": source_message_id,
        "source_quote": source_quote,
        "observed_at": observed_at,
    }


def _critical_sentences(message: Dict[str, Any]) -> List[str]:
    content = str(message.get("content") or "")
    return [
        part.strip()
        for part in re.split(r"(?<=[。！？!?；;])|\n+", content)
        if part.strip() and _fact_category(part)
    ]


def _append_rule_fallbacks(
    facts: List[Dict[str, Any]],
    source_messages: Dict[int, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    covered_quotes = {
        (int(fact["source_message_id"]), _normalize_space(fact["source_quote"]))
        for fact in facts
    }
    for message_id, message in source_messages.items():
        for sentence in _critical_sentences(message):
            normalized_sentence = _normalize_space(sentence)
            if (message_id, normalized_sentence) in covered_quotes:
                continue
            category = _fact_category(normalized_sentence)
            facts.append(
                {
                    "category": category,
                    "statement": normalized_sentence,
                    "status": (
                        "absent"
                        if _contains_negation(normalized_sentence)
                        else "present"
                    ),
                    "source_message_id": message_id,
                    "source_quote": normalized_sentence,
                    "observed_at": str(message.get("timestamp") or ""),
                }
            )
    return facts


def _dedupe_facts(facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped = []
    seen = set()
    for fact in facts:
        if not isinstance(fact, dict):
            continue
        key = (
            fact.get("category"),
            _normalize_space(fact.get("statement")),
            fact.get("source_message_id"),
            _normalize_space(fact.get("source_quote")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(fact)
    return deduped


def _message_groups(messages: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    groups: List[List[Dict[str, Any]]] = []
    for message in messages:
        if not groups or message.get("role") == "user":
            groups.append([message])
        else:
            groups[-1].append(message)
    return groups


def _split_recent_tail(
    messages: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    kept_groups: List[List[Dict[str, Any]]] = []
    kept_count = 0
    kept_tokens = 0
    for group in reversed(_message_groups(messages)):
        group_count = len(group)
        group_tokens = _messages_tokens(group)
        if kept_groups and (
            kept_count + group_count > max(1, CONTEXT_KEEP_RECENT_MESSAGES)
            or kept_tokens + group_tokens > max(1, CONTEXT_KEEP_RECENT_TOKENS)
        ):
            break
        kept_groups.append(group)
        kept_count += group_count
        kept_tokens += group_tokens

    recent = [item for group in reversed(kept_groups) for item in group]
    compact_count = len(messages) - len(recent)
    return messages[:compact_count], recent


def _format_messages(messages: List[Dict[str, Any]]) -> str:
    blocks = []
    for message in messages:
        blocks.append(
            "[message_id={id} role={role} timestamp={timestamp}]\n{content}".format(
                id=message.get("id"),
                role=message.get("role", ""),
                timestamp=message.get("timestamp", ""),
                content=message.get("content", ""),
            )
        )
    return "\n\n".join(blocks)


def _compact_messages(
    previous_summary: str,
    messages: List[Dict[str, Any]],
    *,
    user_id: str,
) -> tuple[str, List[Dict[str, Any]]]:
    llm = get_llm(user_id=user_id)
    if not llm:
        raise RuntimeError("main LLM is unavailable")

    prompt = (
        "你负责压缩医疗对话历史。只总结给出的旧摘要和本批消息，不要回答用户问题。\n"
        "普通对话可以概括；只从 role=user 的消息中提取患者事实，不能把助手建议当成患者事实。\n"
        "过敏、用药与剂量、检查数值、症状发生时间、明确否认必须提取为独立事实。\n"
        "每条事实的 source_message_id 必须来自输入，source_quote 必须逐字复制该消息中的连续原文。\n"
        "不得修改数字、单位和否定关系。冲突事实分别保留，不要自行判断哪个正确。\n"
        "只返回 JSON："
        '{"summary":"简洁历史摘要","medical_facts":['
        '{"category":"allergy|medication|test_result|symptom|negation",'
        '"statement":"事实","status":"present|absent|uncertain",'
        '"source_message_id":1,"source_quote":"连续原文片段"'
        "}]}\n\n"
        f"已有历史摘要：\n{previous_summary or '暂无'}\n\n"
        f"本批待压缩消息：\n{_format_messages(messages)}"
    )
    response = llm.invoke(prompt)
    payload = json.loads(_extract_json_block(coerce_response_text(response)))
    if not isinstance(payload, dict):
        raise ValueError("compression response must be an object")
    summary = str(payload.get("summary") or "").strip()
    raw_facts = payload.get("medical_facts") or []
    if not summary or not isinstance(raw_facts, list):
        raise ValueError("compression response did not match the required schema")

    source_messages = {
        int(item["id"]): item for item in messages if item.get("role") == "user"
    }
    facts = [
        validated
        for raw_fact in raw_facts
        if (validated := _validate_fact(raw_fact, source_messages)) is not None
    ]
    facts = _append_rule_fallbacks(facts, source_messages)
    facts = _dedupe_facts(facts)

    input_tokens = _count_tokens(previous_summary) + _messages_tokens(messages)
    output_tokens = _count_tokens(summary) + _count_tokens(
        json.dumps(facts, ensure_ascii=False)
    )
    if output_tokens >= input_tokens:
        raise ValueError("compression output did not reduce context size")
    return summary, facts


class ContextCompactionService:
    """Build compact, traceable conversation context before routing and generation."""

    @staticmethod
    def _fallback(
        history: List[Dict[str, Any]],
        current_message_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        filtered = [
            item
            for item in history
            if not current_message_id or item.get("id") != current_message_id
        ]
        recent = list(filtered[-max(1, CONTEXT_MAX_MESSAGES) :])
        return {
            "conversation_summary": "",
            "protected_medical_facts": [],
            "recent_history": recent,
            "context_compression_info": {
                "triggered": False,
                "completed": False,
                "fallback": True,
                "recent_messages": len(recent),
            },
        }

    def build_context(
        self,
        *,
        user_id: str,
        session_id: str,
        current_message_id: Optional[int],
        fallback_history: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not CONTEXT_COMPRESSION_ENABLED or not session_id or not current_message_id:
            return self._fallback(fallback_history, current_message_id)

        pending: List[Dict[str, Any]] = []
        try:
            checkpoint = (
                db_service.get_context_checkpoint(
                    session_id,
                    user_id=user_id,
                )
                or {}
            )
            summary = str(checkpoint.get("summary_text") or "")
            saved_facts = list(checkpoint.get("medical_facts") or [])
            covered_message_id = int(checkpoint.get("covered_message_id") or 0)
            pending = db_service.get_chat_history_after(
                session_id,
                user_id=user_id,
                after_message_id=covered_message_id,
                before_message_id=current_message_id,
            )
            before_tokens = _count_tokens(summary) + _messages_tokens(pending)
            should_compact = len(pending) > max(
                1, CONTEXT_MAX_MESSAGES
            ) or before_tokens > max(1, CONTEXT_MAX_TOKENS)
            if not should_compact:
                return {
                    "conversation_summary": summary,
                    "protected_medical_facts": saved_facts,
                    "recent_history": pending,
                    "context_compression_info": {
                        "triggered": False,
                        "completed": False,
                        "fallback": False,
                        "before_tokens": before_tokens,
                        "after_tokens": before_tokens,
                        "recent_messages": len(pending),
                        "checkpoint_version": int(checkpoint.get("version") or 0),
                    },
                }

            to_compact, recent = _split_recent_tail(pending)
            if not to_compact:
                return self._fallback(pending, current_message_id)

            new_summary, new_facts = _compact_messages(
                summary,
                to_compact,
                user_id=user_id,
            )
            merged_facts = _dedupe_facts(saved_facts + new_facts)
            saved = db_service.save_context_checkpoint(
                session_id,
                user_id=user_id,
                summary_text=new_summary,
                medical_facts=merged_facts,
                covered_message_id=int(to_compact[-1]["id"]),
            )
            after_tokens = (
                _count_tokens(new_summary)
                + _count_tokens(json.dumps(merged_facts, ensure_ascii=False))
                + _messages_tokens(recent)
            )
            logger.info(
                "Context compacted user=%s session=%s messages=%d tokens=%d->%d facts=%d version=%d",
                user_id,
                session_id[:8],
                len(to_compact),
                before_tokens,
                after_tokens,
                len(merged_facts),
                saved["version"],
            )
            return {
                "conversation_summary": new_summary,
                "protected_medical_facts": merged_facts,
                "recent_history": recent,
                "context_compression_info": {
                    "triggered": True,
                    "completed": True,
                    "fallback": False,
                    "before_tokens": before_tokens,
                    "after_tokens": after_tokens,
                    "compacted_messages": len(to_compact),
                    "recent_messages": len(recent),
                    "medical_facts": len(merged_facts),
                    "covered_message_id": int(to_compact[-1]["id"]),
                    "checkpoint_version": int(saved["version"]),
                },
            }
        except Exception as exc:
            logger.warning(
                "Context compaction failed for user=%s session=%s: %s",
                user_id,
                session_id[:8],
                exc,
            )
            return self._fallback(
                pending or fallback_history,
                current_message_id,
            )


context_compaction_service = ContextCompactionService()
