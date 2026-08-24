import os
import sys
import time
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.redis_service import redis_service  # noqa: E402
from app.services.semantic_cache_service import (  # noqa: E402
    SemanticCacheLookup,
    semantic_cache_service,
)

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_REDIS_STACK_INTEGRATION") != "1",
    reason="set RUN_REDIS_STACK_INTEGRATION=1 to use a real Redis Stack server",
)


def test_real_redis_stack_entity_filter_and_vector_hit():
    client = redis_service.client()
    assert client is not None
    assert client.ping() is True

    vector = np.zeros(512, dtype=np.float32)
    vector[0] = 1.0
    lookup = SemanticCacheLookup(
        eligible=True,
        entities=("咖啡", "高血压"),
        action="饮用建议",
        constraints=("成人",),
        entity_filter="咖啡__高血压",
        action_filter="饮用建议",
        constraint_filter="成人",
        embedding=vector.tobytes(),
        metadata={
            "entities": ["咖啡", "高血压"],
            "action": "饮用建议",
            "constraints": ["成人"],
        },
    )
    semantic_cache_service._index_ready = False
    key = semantic_cache_service.store_answer(lookup, answer="集成测试回答")
    assert key is not None

    try:
        assert set(client.hkeys(key)) == {
            b"entities",
            b"action",
            b"constraints",
            b"embedding",
            b"answer",
        }
        result = None
        for _ in range(20):
            result = semantic_cache_service.get_answer(lookup)
            if result:
                break
            time.sleep(0.05)
        assert result is not None
        assert result["answer"] == "集成测试回答"
        assert result["cache_hit"] is True

        other_constraint_lookup = SemanticCacheLookup(
            eligible=True,
            entities=("咖啡", "高血压"),
            action="饮用建议",
            constraints=("孕妇",),
            entity_filter="咖啡__高血压",
            action_filter="饮用建议",
            constraint_filter="孕妇",
            embedding=vector.tobytes(),
        )
        assert semantic_cache_service.get_answer(other_constraint_lookup) is None
    finally:
        client.delete(key)
