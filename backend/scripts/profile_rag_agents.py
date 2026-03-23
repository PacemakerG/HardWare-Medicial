"""
Profile the RAG agent pipeline on an evaluation dataset.

Outputs aggregate timings, token estimates, retrieval behavior, and optional
LLM-judge timing/cost signals for the current dataset.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.query_rewriter import QueryRewriterAgent  # noqa: E402
from app.agents.reranker import RerankerAgent  # noqa: E402
from app.agents.retriever import RetrieverAgent  # noqa: E402
from app.core.config import LANGSMITH_PROJECT, LANGSMITH_TRACING  # noqa: E402
from app.core.state import estimate_text_tokens, initialize_conversation_state  # noqa: E402
from app.tools.llm_client import coerce_response_text, get_light_llm  # noqa: E402


def _load_dataset(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return round(values[0], 2)
    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return round(sorted_values[int(rank)], 2)
    weight = rank - low
    value = sorted_values[low] * (1 - weight) + sorted_values[high] * weight
    return round(value, 2)


def _estimate_answer(question: str, contexts: List[Dict[str, Any]]) -> tuple[str, Dict[str, int]]:
    llm = get_light_llm()
    if not llm:
        return "", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    context_text = "\n\n".join(
        f"[CTX-{idx}] {item.get('content', '')[:700]}"
        for idx, item in enumerate(contexts[:4], start=1)
    )
    prompt = (
        "你是医疗知识问答助手，只能依据给定资料回答。\n"
        "要求：\n"
        "1. 用简体中文\n"
        "2. 先给直接结论，再给2条建议\n"
        "3. 如果资料不足，要明确说明不确定\n\n"
        f"问题：{question}\n\n"
        f"资料：\n{context_text or '无'}\n"
    )
    try:
        raw = llm.invoke(prompt)
        answer = coerce_response_text(raw).strip()
    except Exception:
        answer = ""
    prompt_tokens = estimate_text_tokens(prompt)
    completion_tokens = estimate_text_tokens(answer)
    return answer, {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def _estimate_judge(
    sample: Dict[str, Any],
    answer: str,
    contexts: List[Dict[str, Any]],
) -> Dict[str, int]:
    question = str(sample.get("question", ""))
    reference_answer = str(sample.get("reference_answer", ""))
    context_text = "\n\n".join(
        f"[CTX-{idx}] {item.get('content', '')[:700]}"
        for idx, item in enumerate(contexts[:4], start=1)
    )
    prompt = (
        "你是医疗RAG系统评测裁判。请严格根据问题、参考答案和检索证据，对模型回答打分。\n"
        "只返回 JSON："
        '{"correctness": 1-5, "faithfulness": 1-5, "relevance": 1-5}\n'
        "评分含义：\n"
        "- correctness：回答是否与参考答案一致、是否答对核心点\n"
        "- faithfulness：回答是否忠于检索证据、是否存在编造\n"
        "- relevance：回答是否直接回应用户问题\n\n"
        f"用户问题：{question}\n\n"
        f"参考答案：{reference_answer}\n\n"
        f"检索证据：\n{context_text or '无'}\n\n"
        f"模型回答：\n{answer}\n"
    )
    llm = get_light_llm()
    judge_output = ""
    if llm:
        try:
            raw = llm.invoke(prompt)
            judge_output = coerce_response_text(raw).strip()
        except Exception:
            judge_output = ""
    prompt_tokens = estimate_text_tokens(prompt)
    completion_tokens = estimate_text_tokens(judge_output)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


def run_profile(dataset_path: Path, limit: int | None = None) -> Dict[str, Any]:
    samples = _load_dataset(dataset_path)
    if limit is not None and limit > 0:
        samples = samples[:limit]

    node_timings: Dict[str, List[float]] = {
        "query_rewriter": [],
        "rag": [],
        "reranker": [],
    }
    retrieval_counts: List[int] = []
    vector_hits: List[int] = []
    keyword_hits: List[int] = []
    retrieval_query_counts: List[int] = []
    answer_token_totals: List[int] = []
    answer_prompt_tokens: List[int] = []
    answer_completion_tokens: List[int] = []
    judge_token_totals: List[int] = []
    judge_prompt_tokens: List[int] = []
    judge_completion_tokens: List[int] = []
    total_pipeline_ms: List[float] = []
    samples_detail: List[Dict[str, Any]] = []

    for sample in samples:
        state = initialize_conversation_state()
        state["question"] = str(sample.get("question", "")).strip()
        state["domain"] = "medical"
        state["use_rag"] = True
        state["selected_department"] = (
            sample.get("selected_department") or sample.get("expected_department")
        )
        state["selected_department_forced"] = bool(state["selected_department"])

        state = QueryRewriterAgent(state)
        state = RetrieverAgent(state)
        state = RerankerAgent(state)

        profiling = state.get("profiling", {}) or {}
        timing_bucket = profiling.get("node_timings_ms", {}) or {}
        retrieval_bucket = profiling.get("retrieval", {}) or {}

        query_rewriter_ms = float(timing_bucket.get("query_rewriter", 0.0))
        rag_ms = float(timing_bucket.get("rag", 0.0))
        reranker_ms = float(timing_bucket.get("reranker", 0.0))
        total_ms = query_rewriter_ms + rag_ms + reranker_ms

        node_timings["query_rewriter"].append(query_rewriter_ms)
        node_timings["rag"].append(rag_ms)
        node_timings["reranker"].append(reranker_ms)
        total_pipeline_ms.append(total_ms)

        retrieval_counts.append(len(state.get("rag_context") or []))
        vector_hits.append(int(retrieval_bucket.get("vector_hits", 0)))
        keyword_hits.append(int(retrieval_bucket.get("keyword_hits", 0)))
        retrieval_query_counts.append(len(state.get("retrieval_queries") or []))

        answer, answer_tokens = _estimate_answer(
            state.get("question", ""),
            list(state.get("rag_context") or []),
        )
        judge_tokens = _estimate_judge(sample, answer, list(state.get("rag_context") or []))

        answer_prompt_tokens.append(answer_tokens["prompt_tokens"])
        answer_completion_tokens.append(answer_tokens["completion_tokens"])
        answer_token_totals.append(answer_tokens["total_tokens"])
        judge_prompt_tokens.append(judge_tokens["prompt_tokens"])
        judge_completion_tokens.append(judge_tokens["completion_tokens"])
        judge_token_totals.append(judge_tokens["total_tokens"])

        samples_detail.append(
            {
                "id": sample.get("id", ""),
                "question": sample.get("question", ""),
                "selected_department": sample.get("selected_department"),
                "node_timings_ms": {
                    "query_rewriter": round(query_rewriter_ms, 2),
                    "rag": round(rag_ms, 2),
                    "reranker": round(reranker_ms, 2),
                    "total": round(total_ms, 2),
                },
                "retrieval_context_count": len(state.get("rag_context") or []),
                "retrieval_query_count": len(state.get("retrieval_queries") or []),
                "vector_hits": int(retrieval_bucket.get("vector_hits", 0)),
                "keyword_hits": int(retrieval_bucket.get("keyword_hits", 0)),
                "answer_tokens_est": answer_tokens,
                "judge_tokens_est": judge_tokens,
            }
        )

    summary = {
        "dataset_samples": len(samples_detail),
        "langsmith_tracing_enabled": bool(LANGSMITH_TRACING),
        "langsmith_project": LANGSMITH_PROJECT,
        "node_timing_ms": {
            name: {
                "avg": round(mean(values), 2) if values else 0.0,
                "p50": round(median(values), 2) if values else 0.0,
                "p95": _percentile(values, 0.95),
            }
            for name, values in node_timings.items()
        },
        "pipeline_total_ms": {
            "avg": round(mean(total_pipeline_ms), 2) if total_pipeline_ms else 0.0,
            "p50": round(median(total_pipeline_ms), 2) if total_pipeline_ms else 0.0,
            "p95": _percentile(total_pipeline_ms, 0.95),
        },
        "retrieval_behavior": {
            "avg_context_count": round(mean(retrieval_counts), 2) if retrieval_counts else 0.0,
            "avg_retrieval_query_count": round(mean(retrieval_query_counts), 2) if retrieval_query_counts else 0.0,
            "avg_vector_hits": round(mean(vector_hits), 2) if vector_hits else 0.0,
            "avg_keyword_hits": round(mean(keyword_hits), 2) if keyword_hits else 0.0,
        },
        "token_estimates": {
            "answer_generation": {
                "avg_prompt_tokens": round(mean(answer_prompt_tokens), 2) if answer_prompt_tokens else 0.0,
                "avg_completion_tokens": round(mean(answer_completion_tokens), 2) if answer_completion_tokens else 0.0,
                "avg_total_tokens": round(mean(answer_token_totals), 2) if answer_token_totals else 0.0,
            },
            "llm_judge": {
                "avg_prompt_tokens": round(mean(judge_prompt_tokens), 2) if judge_prompt_tokens else 0.0,
                "avg_completion_tokens": round(mean(judge_completion_tokens), 2) if judge_completion_tokens else 0.0,
                "avg_total_tokens": round(mean(judge_token_totals), 2) if judge_token_totals else 0.0,
            },
            "combined_avg_total_tokens": round(
                mean(
                    answer + judge
                    for answer, judge in zip(answer_token_totals, judge_token_totals)
                ),
                2,
            ) if answer_token_totals and judge_token_totals else 0.0,
        },
    }

    return {"summary": summary, "samples": samples_detail}


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile the RAG pipeline on an eval dataset.")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(BACKEND_ROOT / "data" / "eval" / "rag_eval_dataset_v1.jsonl"),
        help="JSONL dataset path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only profile the first N samples. 0 means all.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(BACKEND_ROOT / "data" / "eval" / "rag_agent_profile_v1.json"),
        help="Output JSON path.",
    )
    args = parser.parse_args()

    result = run_profile(
        dataset_path=Path(args.dataset),
        limit=int(args.limit) if int(args.limit) > 0 else None,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
