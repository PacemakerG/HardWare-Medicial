"""
Offline RAG evaluation runner for MediGenius.

Focus:
1. Retrieval quality: Top1 / Recall@K / MRR
2. LLM Judge quality: correctness / faithfulness / relevance

Usage:
  python backend/scripts/evaluate_rag_pipeline.py \
    --dataset backend/data/eval/rag_eval_dataset_v1.jsonl \
    --top-k 5 \
    --with-judge
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.agents.query_rewriter import QueryRewriterAgent  # noqa: E402
from app.agents.reranker import RerankerAgent  # noqa: E402
from app.agents.retriever import RetrieverAgent  # noqa: E402
from app.core.state import initialize_conversation_state  # noqa: E402
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


def _normalize_text(text: str) -> str:
    return " ".join(str(text or "").lower().split())


def _match_chunk(chunk: Dict[str, Any], sample: Dict[str, Any]) -> bool:
    metadata = chunk.get("metadata", {}) or {}
    chunk_text = _normalize_text(chunk.get("content", ""))
    expected_department = _normalize_text(sample.get("expected_department", ""))
    expected_source_book = _normalize_text(sample.get("expected_source_book", ""))
    expected_anchor_text = _normalize_text(sample.get("expected_anchor_text", ""))
    expected_keywords = [_normalize_text(item) for item in sample.get("expected_keywords", [])]

    if expected_department and _normalize_text(metadata.get("department", "")) != expected_department:
        return False

    soft_checks: List[bool] = []
    if expected_source_book:
        soft_checks.append(expected_source_book in _normalize_text(metadata.get("source_book", "")))
    if expected_anchor_text:
        soft_checks.append(expected_anchor_text in chunk_text)
    if expected_keywords:
        keyword_hits = sum(1 for keyword in expected_keywords if keyword and keyword in chunk_text)
        soft_checks.append(keyword_hits >= 1)

    if not soft_checks:
        return bool(expected_department)

    required_hits = 2 if len(soft_checks) >= 2 else 1
    return sum(1 for item in soft_checks if item) >= required_hits


def _retrieval_metrics(ranked_chunks: List[Dict[str, Any]], sample: Dict[str, Any], top_k: int) -> Tuple[int, int, float]:
    top1 = 0
    recall = 0
    mrr = 0.0
    for idx, chunk in enumerate(ranked_chunks[: max(1, top_k)], start=1):
        if not _match_chunk(chunk, sample):
            continue
        if idx == 1:
            top1 = 1
        recall = 1
        mrr = 1.0 / idx
        break
    return top1, recall, mrr


def _build_answer(question: str, contexts: List[Dict[str, Any]]) -> str:
    llm = get_light_llm()
    if not llm:
        return ""
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
        return coerce_response_text(raw).strip()
    except Exception:
        return ""


def _judge_answer(sample: Dict[str, Any], answer: str, contexts: List[Dict[str, Any]]) -> Dict[str, float]:
    llm = get_light_llm()
    if not llm:
        return {
            "correctness": 0.0,
            "faithfulness": 0.0,
            "relevance": 0.0,
        }

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
    try:
        raw = llm.invoke(prompt)
        text = coerce_response_text(raw)
        start = text.find("{")
        end = text.rfind("}")
        payload = json.loads(text[start : end + 1]) if start != -1 and end > start else {}
        return {
            "correctness": float(payload.get("correctness", 0.0)),
            "faithfulness": float(payload.get("faithfulness", 0.0)),
            "relevance": float(payload.get("relevance", 0.0)),
        }
    except Exception:
        return {
            "correctness": 0.0,
            "faithfulness": 0.0,
            "relevance": 0.0,
        }


def _run_single_sample(sample: Dict[str, Any], top_k: int, with_judge: bool) -> Dict[str, Any]:
    question = str(sample.get("question", "")).strip()
    if not question:
        return {}

    state = initialize_conversation_state()
    state["question"] = question
    state["domain"] = "medical"
    state["use_rag"] = True

    selected_department = sample.get("selected_department") or sample.get("expected_department")
    if selected_department:
        state["selected_department"] = str(selected_department)
        state["selected_department_forced"] = True

    state = QueryRewriterAgent(state)
    state = RetrieverAgent(state)
    state = RerankerAgent(state)

    ranked_chunks = list(state.get("rag_context") or [])
    top1, recall, mrr = _retrieval_metrics(ranked_chunks, sample, top_k=top_k)

    result = {
        "id": sample.get("id", ""),
        "question": question,
        "top1_hit": top1,
        "recall_hit": recall,
        "mrr": mrr,
        "retrieved_context_count": len(ranked_chunks),
        "retrieval_query": state.get("retrieval_query"),
        "retrieval_queries": state.get("retrieval_queries", []),
        "matched": bool(recall),
    }

    if with_judge:
        answer = _build_answer(question, ranked_chunks)
        judge = _judge_answer(sample, answer, ranked_chunks)
        result["answer"] = answer
        result["judge"] = judge

    return result


def run_eval(
    dataset_path: Path,
    top_k: int,
    with_judge: bool,
    output_path: Path | None = None,
    limit: int | None = None,
) -> Dict[str, Any]:
    samples = _load_dataset(dataset_path)
    if not samples:
        raise ValueError(f"Dataset empty: {dataset_path}")
    if limit is not None and limit > 0:
        samples = samples[:limit]

    results: List[Dict[str, Any]] = []
    top1_scores: List[int] = []
    recall_scores: List[int] = []
    mrr_scores: List[float] = []
    judge_correctness: List[float] = []
    judge_faithfulness: List[float] = []
    judge_relevance: List[float] = []

    for sample in samples:
        item = _run_single_sample(sample, top_k=top_k, with_judge=with_judge)
        if not item:
            continue
        results.append(item)
        top1_scores.append(int(item["top1_hit"]))
        recall_scores.append(int(item["recall_hit"]))
        mrr_scores.append(float(item["mrr"]))
        if with_judge and isinstance(item.get("judge"), dict):
            judge_correctness.append(float(item["judge"].get("correctness", 0.0)))
            judge_faithfulness.append(float(item["judge"].get("faithfulness", 0.0)))
            judge_relevance.append(float(item["judge"].get("relevance", 0.0)))

    summary = {
        "samples": len(results),
        "top1_accuracy": round(mean(top1_scores), 4) if top1_scores else 0.0,
        f"recall@{top_k}": round(mean(recall_scores), 4) if recall_scores else 0.0,
        "mrr": round(mean(mrr_scores), 4) if mrr_scores else 0.0,
        "judge_correctness_avg": round(mean(judge_correctness), 4) if judge_correctness else 0.0,
        "judge_faithfulness_avg": round(mean(judge_faithfulness), 4) if judge_faithfulness else 0.0,
        "judge_relevance_avg": round(mean(judge_relevance), 4) if judge_relevance else 0.0,
        "judge_pass_rate": round(
            mean(
                1 if min(
                    float(item.get("judge", {}).get("correctness", 0.0)),
                    float(item.get("judge", {}).get("faithfulness", 0.0)),
                    float(item.get("judge", {}).get("relevance", 0.0)),
                ) >= 4.0 else 0
                for item in results
                if item.get("judge")
            ),
            4,
        ) if judge_correctness else 0.0,
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"summary": summary, "results": results}
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return {"summary": summary, "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate MediGenius RAG quality.")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(BACKEND_ROOT / "data" / "eval" / "rag_eval_dataset_v1.jsonl"),
        help="JSONL dataset path.",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-K for Recall@K / MRR.")
    parser.add_argument(
        "--with-judge",
        action="store_true",
        help="Enable LLM Judge for correctness / faithfulness / relevance.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(BACKEND_ROOT / "data" / "eval" / "rag_eval_result_v1.json"),
        help="Detailed result output path.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only evaluate the first N samples. 0 means all.",
    )
    args = parser.parse_args()

    result = run_eval(
        dataset_path=Path(args.dataset),
        top_k=max(1, int(args.top_k)),
        with_judge=bool(args.with_judge),
        output_path=Path(args.output) if args.output else None,
        limit=int(args.limit) if int(args.limit) > 0 else None,
    )
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
