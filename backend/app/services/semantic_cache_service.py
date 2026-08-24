"""
MediGenius — services/semantic_cache_service.py
Redis Stack semantic cache with structured semantic filtering and vector search.
"""

import json
import re
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from app.core.config import (
    SEMANTIC_CACHE_EMBEDDING_DIMENSION,
    SEMANTIC_CACHE_EMBEDDING_MODEL,
    SEMANTIC_CACHE_ENABLED,
    SEMANTIC_CACHE_EXTRACTION_MODEL,
    SEMANTIC_CACHE_INDEX_NAME,
    SEMANTIC_CACHE_KEY_PREFIX,
    SEMANTIC_CACHE_SIMILARITY_THRESHOLD,
    SEMANTIC_CACHE_TTL_SECONDS,
)
from app.core.logging_config import logger
from app.services.redis_service import redis_service
from app.tools.llm_client import coerce_response_text, get_light_llm

_EMPTY_CONSTRAINT_FILTER = "_none_"


@dataclass
class SemanticCacheLookup:
    eligible: bool
    entities: tuple[str, ...] = ()
    action: str = ""
    constraints: tuple[str, ...] = ()
    entity_filter: str = ""
    action_filter: str = ""
    constraint_filter: str = ""
    embedding: bytes = b""
    metadata: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


class SemanticCacheService:
    """Global medical-answer cache backed by Redis Stack Search."""

    def __init__(self) -> None:
        self._embedding_model = None
        self._embedding_lock = threading.Lock()
        self._index_ready = False
        self._index_lock = threading.Lock()

    @staticmethod
    def _extract_json_object(text: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
        except (TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def _normalize_semantic_field(value: Any) -> str:
        normalized = str(value or "").strip()
        normalized = re.sub(r"[\s|]+", "", normalized)
        normalized = re.sub(
            r"^[，。！？、；：,.!?;:]+|[，。！？、；：,.!?;:]+$",
            "",
            normalized,
        )
        if re.fullmatch(r"[A-Za-z0-9_\-]+", normalized):
            normalized = normalized.lower()
        return normalized[:80]

    def _extract_signature(
        self,
        query: str,
        *,
        user_id: str,
    ) -> tuple[tuple[str, ...], str, tuple[str, ...]]:
        llm = get_light_llm(
            user_id=user_id,
            model_override=SEMANTIC_CACHE_EXTRACTION_MODEL,
        )
        if llm is None:
            return (), "", ()

        prompt = f"""你是医疗问答语义缓存的结构化抽取器。请判断哪些字段决定已有答案能否被安全复用。

请只返回严格 JSON，格式为：
{{"entities":["实体1","实体2"],"action":"标准动作","constraints":["约束1","约束2"]}}

字段规则：
1. entities：疾病、症状、药物、检查、治疗或行为对象；同义词必须归一化，例如“血压高”统一为“高血压”。
2. action：问题要执行或询问的核心动作，归一化为简短动宾词组，例如“能不能喝”统一为“饮用建议”，“为何检查”统一为“检查必要性”。
3. constraints：会改变答案的人群、年龄、孕期、剂量、频率、时长、疾病阶段、严重程度、否定条件等；没有时返回空数组。
4. “患者”“病人”等泛化称呼不是约束；同义约束必须统一为相同名称。
5. 不要输出疑问词、语气词、解释或 JSON 之外的内容。

问题：{query}
"""
        try:
            response = llm.invoke(prompt)
            payload = self._extract_json_object(coerce_response_text(response))
        except Exception as exc:
            logger.warning("Semantic cache signature extraction failed: %s", exc)
            return (), "", ()

        raw_entities = payload.get("entities")
        raw_action = payload.get("action")
        raw_constraints = payload.get("constraints")
        if (
            not isinstance(raw_entities, list)
            or not isinstance(raw_action, str)
            or not isinstance(raw_constraints, list)
        ):
            return (), "", ()
        entities = {
            value
            for item in raw_entities
            if (value := self._normalize_semantic_field(item))
        }
        action = self._normalize_semantic_field(raw_action)
        constraints = {
            value
            for item in raw_constraints
            if (value := self._normalize_semantic_field(item))
        }
        if not entities or not action:
            return (), "", ()
        return tuple(sorted(entities)), action, tuple(sorted(constraints))

    def _get_embedding_model(self):
        if self._embedding_model is not None:
            return self._embedding_model
        with self._embedding_lock:
            if self._embedding_model is not None:
                return self._embedding_model
            try:
                from sentence_transformers import SentenceTransformer

                self._embedding_model = SentenceTransformer(
                    SEMANTIC_CACHE_EMBEDDING_MODEL,
                    device="cpu",
                )
                logger.info(
                    "Semantic cache embedding model loaded (%s)",
                    SEMANTIC_CACHE_EMBEDDING_MODEL,
                )
            except Exception as exc:
                logger.error("Semantic cache embedding model unavailable: %s", exc)
                return None
        return self._embedding_model

    def _embed_query(self, query: str) -> bytes:
        model = self._get_embedding_model()
        if model is None:
            return b""
        try:
            vector = model.encode(
                [query],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
            array = np.asarray(vector, dtype=np.float32)
        except Exception as exc:
            logger.warning("Semantic cache embedding failed: %s", exc)
            return b""
        if array.ndim != 1 or array.size != SEMANTIC_CACHE_EMBEDDING_DIMENSION:
            logger.error(
                "Semantic cache embedding dimension mismatch: expected=%s actual=%s",
                SEMANTIC_CACHE_EMBEDDING_DIMENSION,
                array.size,
            )
            return b""
        return array.tobytes()

    @staticmethod
    def _escape_tag_value(value: str) -> str:
        return re.sub(r"([\\,.<>{}\[\]\"':;!@#$%^&*()\-+=~|/ ])", r"\\\1", value)

    def _ensure_index(self, client) -> bool:
        if self._index_ready:
            return True
        with self._index_lock:
            if self._index_ready:
                return True
            try:
                client.execute_command("FT.INFO", SEMANTIC_CACHE_INDEX_NAME)
            except Exception as exc:
                message = str(exc).lower()
                if "unknown command" in message:
                    logger.error(
                        "Redis Stack Search is unavailable; use redis/redis-stack-server"
                    )
                    return False
                missing_index_markers = (
                    "unknown index",
                    "no such index",
                    "index not found",
                    "search_index_not_found",
                )
                if not any(marker in message for marker in missing_index_markers):
                    logger.warning("Semantic cache index inspection failed: %s", exc)
                    return False
                try:
                    client.execute_command(
                        "FT.CREATE",
                        SEMANTIC_CACHE_INDEX_NAME,
                        "ON",
                        "HASH",
                        "PREFIX",
                        "1",
                        SEMANTIC_CACHE_KEY_PREFIX,
                        "SCHEMA",
                        "entities",
                        "TAG",
                        "SEPARATOR",
                        "|",
                        "action",
                        "TAG",
                        "SEPARATOR",
                        "|",
                        "constraints",
                        "TAG",
                        "SEPARATOR",
                        "|",
                        "embedding",
                        "VECTOR",
                        "HNSW",
                        "6",
                        "TYPE",
                        "FLOAT32",
                        "DIM",
                        str(SEMANTIC_CACHE_EMBEDDING_DIMENSION),
                        "DISTANCE_METRIC",
                        "COSINE",
                    )
                except Exception as create_exc:
                    logger.error("Semantic cache index creation failed: %s", create_exc)
                    return False
            self._index_ready = True
            return True

    def build_lookup(
        self,
        *,
        query: str,
        user_id: str = "anonymous",
    ) -> SemanticCacheLookup:
        if not SEMANTIC_CACHE_ENABLED:
            return SemanticCacheLookup(False, reason="disabled")
        if not redis_service.available():
            return SemanticCacheLookup(False, reason="redis_unavailable")

        entities, action, constraints = self._extract_signature(
            query,
            user_id=user_id,
        )
        if not entities or not action:
            return SemanticCacheLookup(False, reason="signature_unavailable")

        embedding = self._embed_query(query)
        if not embedding:
            return SemanticCacheLookup(
                False,
                entities=entities,
                action=action,
                constraints=constraints,
                metadata={
                    "entities": list(entities),
                    "action": action,
                    "constraints": list(constraints),
                },
                reason="embedding_unavailable",
            )

        entity_filter = "__".join(entities)
        action_filter = action
        constraint_filter = (
            "__".join(constraints) if constraints else _EMPTY_CONSTRAINT_FILTER
        )
        return SemanticCacheLookup(
            True,
            entities=entities,
            action=action,
            constraints=constraints,
            entity_filter=entity_filter,
            action_filter=action_filter,
            constraint_filter=constraint_filter,
            embedding=embedding,
            metadata={
                "entities": list(entities),
                "action": action,
                "constraints": list(constraints),
            },
        )

    @staticmethod
    def _decode(value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8")
        return str(value or "")

    def get_answer(self, lookup: SemanticCacheLookup) -> Optional[dict[str, Any]]:
        if not lookup.eligible:
            return None
        client = redis_service.client()
        if client is None or not self._ensure_index(client):
            return None

        escaped_entities = self._escape_tag_value(lookup.entity_filter)
        escaped_action = self._escape_tag_value(lookup.action_filter)
        escaped_constraints = self._escape_tag_value(lookup.constraint_filter)
        query = (
            f"(@entities:{{{escaped_entities}}}"
            f" @action:{{{escaped_action}}}"
            f" @constraints:{{{escaped_constraints}}})"
            "=>[KNN 1 @embedding $query_vector AS distance]"
        )
        try:
            result = client.execute_command(
                "FT.SEARCH",
                SEMANTIC_CACHE_INDEX_NAME,
                query,
                "PARAMS",
                "2",
                "query_vector",
                lookup.embedding,
                "SORTBY",
                "distance",
                "ASC",
                "RETURN",
                "2",
                "answer",
                "distance",
                "DIALECT",
                "2",
            )
        except Exception as exc:
            logger.warning("Semantic cache vector search failed: %s", exc)
            return None

        if not isinstance(result, (list, tuple)) or not result or int(result[0]) == 0:
            return None
        if len(result) < 3 or not isinstance(result[2], (list, tuple)):
            return None
        fields = result[2]
        row = {
            self._decode(fields[index]): fields[index + 1]
            for index in range(0, len(fields) - 1, 2)
        }
        try:
            distance = float(self._decode(row.get("distance")))
        except (TypeError, ValueError):
            return None
        similarity = 1.0 - distance
        if similarity < SEMANTIC_CACHE_SIMILARITY_THRESHOLD:
            return None

        answer = self._decode(row.get("answer"))
        if not answer:
            return None
        lookup.metadata["similarity"] = round(similarity, 6)
        return {
            "answer": answer,
            "source": "Semantic Cache",
            "flow_trace": ["semantic_cache"],
            "cache_hit": True,
            "similarity": similarity,
        }

    def store_answer(
        self,
        lookup: SemanticCacheLookup,
        *,
        answer: str,
        source: str = "",
        flow_trace: Optional[list[str]] = None,
    ) -> Optional[str]:
        del source, flow_trace
        if not lookup.eligible or not answer:
            return None
        client = redis_service.client()
        if client is None or not self._ensure_index(client):
            return None

        key = f"{SEMANTIC_CACHE_KEY_PREFIX}{uuid.uuid4()}"
        try:
            client.hset(
                key,
                mapping={
                    "entities": lookup.entity_filter,
                    "action": lookup.action_filter,
                    "constraints": lookup.constraint_filter,
                    "embedding": lookup.embedding,
                    "answer": answer,
                },
            )
            client.expire(key, int(SEMANTIC_CACHE_TTL_SECONDS))
            return key
        except Exception as exc:
            logger.warning("Semantic cache write failed: %s", exc)
            return None


semantic_cache_service = SemanticCacheService()
