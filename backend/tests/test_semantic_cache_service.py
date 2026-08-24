import numpy as np

from app.services.semantic_cache_service import SemanticCacheService, redis_service


class FakeRedis:
    def __init__(self):
        self.index_exists = False
        self.create_args = None
        self.hashes = {}
        self.expirations = {}
        self.search_result = [0]
        self.last_search = None

    def execute_command(self, *args):
        command = args[0]
        if command == "FT.INFO":
            if not self.index_exists:
                raise RuntimeError("Unknown Index name")
            return [b"index_name", b"mg:semcache:index"]
        if command == "FT.CREATE":
            self.index_exists = True
            self.create_args = args
            return b"OK"
        if command == "FT.SEARCH":
            self.last_search = args
            return self.search_result
        raise AssertionError(f"Unexpected Redis command: {command}")

    def hset(self, key, mapping):
        self.hashes[key] = mapping

    def expire(self, key, seconds):
        self.expirations[key] = seconds


def _build_lookup(monkeypatch, query="高血压患者可以喝咖啡吗？"):
    service = SemanticCacheService()
    fake_redis = FakeRedis()
    vector = np.ones(512, dtype=np.float32).tobytes()
    monkeypatch.setattr(redis_service, "available", lambda: True)
    monkeypatch.setattr(redis_service, "client", lambda: fake_redis)
    monkeypatch.setattr(
        service,
        "_extract_signature",
        lambda query, user_id: (
            ("咖啡", "高血压"),
            "饮用建议",
            ("成人",),
        ),
    )
    monkeypatch.setattr(service, "_embed_query", lambda query: vector)
    lookup = service.build_lookup(query=query)
    return service, fake_redis, lookup, vector


def test_lookup_uses_structured_signature_and_question_vector(monkeypatch):
    _, _, lookup, vector = _build_lookup(monkeypatch)

    assert lookup.eligible is True
    assert lookup.entity_filter == "咖啡__高血压"
    assert lookup.action_filter == "饮用建议"
    assert lookup.constraint_filter == "成人"
    assert lookup.embedding == vector
    assert lookup.metadata == {
        "entities": ["咖啡", "高血压"],
        "action": "饮用建议",
        "constraints": ["成人"],
    }


def test_high_risk_text_is_not_special_cased(monkeypatch):
    _, _, lookup, _ = _build_lookup(monkeypatch, "胸痛伴呼吸困难怎么办？")

    assert lookup.eligible is True


def test_store_writes_five_hash_fields_and_uuid_key(monkeypatch):
    service, fake_redis, lookup, _ = _build_lookup(monkeypatch)

    service.store_answer(lookup, answer="测试回答")

    assert len(fake_redis.hashes) == 1
    key, value = next(iter(fake_redis.hashes.items()))
    assert key.startswith("mg:semcache:item:")
    assert set(value) == {
        "entities",
        "action",
        "constraints",
        "embedding",
        "answer",
    }
    assert value["entities"] == "咖啡__高血压"
    assert value["action"] == "饮用建议"
    assert value["constraints"] == "成人"
    assert fake_redis.expirations[key] == 86400
    assert "action" in fake_redis.create_args
    assert "constraints" in fake_redis.create_args


def test_vector_search_returns_answer_above_threshold(monkeypatch):
    service, fake_redis, lookup, _ = _build_lookup(monkeypatch)
    fake_redis.search_result = [
        1,
        b"mg:semcache:item:abc",
        [b"answer", "可以少量饮用。".encode(), b"distance", b"0.05"],
    ]

    cached = service.get_answer(lookup)

    assert cached["answer"] == "可以少量饮用。"
    assert cached["cache_hit"] is True
    assert cached["similarity"] == 0.95
    assert "@entities:{咖啡__高血压}" in fake_redis.last_search[2]
    assert "@action:{饮用建议}" in fake_redis.last_search[2]
    assert "@constraints:{成人}" in fake_redis.last_search[2]


def test_vector_search_rejects_answer_below_threshold(monkeypatch):
    service, fake_redis, lookup, _ = _build_lookup(monkeypatch)
    fake_redis.search_result = [
        1,
        b"mg:semcache:item:abc",
        [b"answer", b"wrong", b"distance", b"0.25"],
    ]

    assert service.get_answer(lookup) is None


def test_qwen_extracts_and_normalizes_complete_signature(monkeypatch):
    service = SemanticCacheService()
    captured = {}

    class FakeLLM:
        def invoke(self, prompt):
            captured["prompt"] = prompt
            return type(
                "Response",
                (),
                {"content": """```json
{"entities":[" 高血压 ","咖啡","咖啡"],"action":" 饮用建议 ","constraints":["成人"," 每天一次 "]}
```"""},
            )()

    def fake_get_light_llm(*, user_id, model_override):
        captured["user_id"] = user_id
        captured["model"] = model_override
        return FakeLLM()

    monkeypatch.setattr(
        "app.services.semantic_cache_service.get_light_llm",
        fake_get_light_llm,
    )

    signature = service._extract_signature(
        "高血压患者每天能喝一次咖啡吗？",
        user_id="user-1",
    )

    assert signature == (
        ("咖啡", "高血压"),
        "饮用建议",
        ("成人", "每天一次"),
    )
    assert captured["model"] == "qwen3.5-flash"
    assert captured["user_id"] == "user-1"
    assert "constraints" in captured["prompt"]


def test_empty_constraints_use_exact_match_sentinel(monkeypatch):
    service, _, lookup, _ = _build_lookup(monkeypatch)
    monkeypatch.setattr(
        service,
        "_extract_signature",
        lambda query, user_id: (("咖啡", "高血压"), "饮用建议", ()),
    )

    lookup = service.build_lookup(query="高血压患者可以喝咖啡吗？")

    assert lookup.eligible is True
    assert lookup.constraints == ()
    assert lookup.constraint_filter == "_none_"


def test_missing_structured_signature_is_a_cache_miss(monkeypatch):
    service = SemanticCacheService()
    monkeypatch.setattr(redis_service, "available", lambda: True)
    monkeypatch.setattr(
        service,
        "_extract_signature",
        lambda query, user_id: ((), "", ()),
    )

    lookup = service.build_lookup(query="你好")

    assert lookup.eligible is False
    assert lookup.reason == "signature_unavailable"
