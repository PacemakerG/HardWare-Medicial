"""Evaluate Redis Stack semantic-cache decisions and end-to-end latency."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import (  # noqa: E402
    KNOWLEDGE_ROOT_DIR,
    SEMANTIC_CACHE_EXTRACTION_MODEL,
)
from app.services.chat_service import chat_service  # noqa: E402
from app.services.database_service import db_service  # noqa: E402
from app.services.redis_service import redis_service  # noqa: E402
from app.services.semantic_cache_service import (  # noqa: E402
    SemanticCacheLookup,
    semantic_cache_service,
)
from app.tools.es_client import (  # noqa: E402
    bulk_index_documents,
    ensure_es_index,
    es_enabled,
)
from app.tools.llm_client import get_light_llm, get_llm  # noqa: E402
from app.tools.pdf_loader import process_knowledge_library  # noqa: E402
from app.tools.vector_store import get_or_create_vectorstore  # noqa: E402

DEFAULT_DATASET = BACKEND_ROOT / "data" / "eval" / "redis" / "dataset_50.json"
DEFAULT_OUTPUT = BACKEND_ROOT / "data" / "eval" / "redis" / "result.json"
EVAL_VECTOR_STORE = "/tmp/medagent-chroma-eval"


def load_dataset(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if len(payload.get("samples") or []) != 50:
        raise ValueError("Redis dataset must contain exactly 50 question pairs")
    return payload


def preflight() -> None:
    missing = []
    client = redis_service.client()
    if client is None or not semantic_cache_service._ensure_index(client):
        missing.append("Redis Stack Search")
    if (
        get_light_llm(
            user_id="redis-eval",
            model_override=SEMANTIC_CACHE_EXTRACTION_MODEL,
        )
        is None
    ):
        missing.append("qwen3.5-flash for cache signature extraction")
    if get_llm(user_id="redis-eval") is None:
        missing.append("main LLM for full-RAG latency")
    if not es_enabled() or not ensure_es_index():
        missing.append("Elasticsearch")
    if missing:
        raise RuntimeError("Redis evaluation requires: " + ", ".join(missing))


def prepare_application() -> None:
    db_service.init_db()
    documents = process_knowledge_library(KNOWLEDGE_ROOT_DIR)
    if (
        get_or_create_vectorstore(
            documents=documents,
            persist_dir=EVAL_VECTOR_STORE,
        )
        is None
    ):
        raise RuntimeError("Vector store initialization failed")
    if not bulk_index_documents(documents):
        raise RuntimeError("Elasticsearch knowledge index initialization failed")
    chat_service.initialize_workflow()


async def _full_rag_latency(question: str, sample_id: str) -> float:
    original_build_lookup = semantic_cache_service.build_lookup
    semantic_cache_service.build_lookup = lambda **_: SemanticCacheLookup(  # type: ignore[method-assign]
        False,
        reason="latency_benchmark_bypass",
    )
    try:
        started = perf_counter()
        await chat_service.process_message(
            f"redis-eval-full-{sample_id}",
            question,
            user_id="redis-eval",
        )
        return (perf_counter() - started) * 1000.0
    finally:
        semantic_cache_service.build_lookup = original_build_lookup  # type: ignore[method-assign]


async def evaluate(dataset: dict[str, Any]) -> dict[str, Any]:
    rows = []
    full_rag_times = []
    cache_hit_times = []
    client = redis_service.client()
    if client is None:
        raise RuntimeError("Redis unavailable after preflight")
    stale_keys = list(client.scan_iter(match="mg:semcache:item:*"))
    if stale_keys:
        client.delete(*stale_keys)

    for sample in dataset["samples"]:
        cached_lookup = semantic_cache_service.build_lookup(
            query=sample["cached_question"],
            user_id="redis-eval",
        )
        cache_key = semantic_cache_service.store_answer(
            cached_lookup,
            answer=sample["cached_answer"],
        )
        try:
            cache_started = perf_counter()
            probe_lookup = semantic_cache_service.build_lookup(
                query=sample["probe_question"],
                user_id="redis-eval",
            )
            cached = semantic_cache_service.get_answer(probe_lookup)
            cache_elapsed_ms = (perf_counter() - cache_started) * 1000.0
            actual_hit = cached is not None
            row = {
                "id": sample["id"],
                "expected_hit": bool(sample["expected_hit"]),
                "actual_hit": actual_hit,
                "correct": actual_hit == bool(sample["expected_hit"]),
            }

            if sample["expected_hit"] and actual_hit:
                cache_hit_times.append(cache_elapsed_ms)
                full_rag_times.append(
                    await _full_rag_latency(sample["probe_question"], sample["id"])
                )
            rows.append(row)
        finally:
            if cache_key:
                client.delete(cache_key)

    if not cache_hit_times:
        raise RuntimeError("No positive cache sample produced an end-to-end cache hit")
    full_average = mean(full_rag_times)
    cache_average = mean(cache_hit_times)
    return {
        "metadata": {
            "dataset": dataset["metadata"]["name"],
            "samples": 50,
            "implementation": (
                "qwen3.5-flash structured extraction + exact "
                "entities/action/constraints TAG filters + "
                "Redis Stack HNSW cosine search"
            ),
            "metric_definitions": {
                "cache_hit_accuracy": "50对问题中命中/未命中判断正确的样本数 / 50",
                "average_latency": "成功命中的正样本分别走完整RAG与实体抽取、向量化、Redis Search和读取回答链路的平均耗时",
            },
        },
        "metrics": {
            "cache_hit_accuracy": round(mean(row["correct"] for row in rows) * 100, 4),
            "average_latency_ms": {
                "full_rag": round(full_average, 4),
                "cache_hit": round(cache_average, 4),
                "reduction": round(
                    (full_average - cache_average) / full_average * 100, 4
                ),
            },
        },
        "samples": rows,
    }


async def async_main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    dataset = load_dataset(Path(args.dataset))
    preflight()
    prepare_application()
    result = await evaluate(dataset)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(async_main())
