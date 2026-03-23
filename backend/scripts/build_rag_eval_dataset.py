"""
Build a document-grounded RAG evaluation dataset from the current knowledge library.

The generator is deterministic and does not require an LLM:
- samples high-quality chunks from each department book
- converts chunk evidence into retrieval questions via templates
- writes JSONL for retrieval + LLM-judge evaluation

Usage:
  python backend/scripts/build_rag_eval_dataset.py \
    --output backend/data/eval/rag_eval_dataset_v1.jsonl \
    --per-department 12
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import KNOWLEDGE_ROOT_DIR  # noqa: E402
from app.core.medical_taxonomy import department_display_name, extract_query_terms  # noqa: E402
from app.tools.pdf_loader import process_knowledge_library  # noqa: E402

NOISE_PATTERNS = (
    "notice",
    "internet archive",
    "page 0",
    "page 1",
    "教材",
    "主编",
    "出版",
    "人民卫生出版社",
    "copyright",
    "isbn",
)
GENERIC_TERMS = {
    "治疗",
    "诊断",
    "检查",
    "患者",
    "疾病",
    "临床",
    "表现",
    "常见",
    "可以",
    "需要",
    "一般",
    "病变",
    "症状",
    "处理",
}
TOPIC_SUFFIXES = (
    "炎",
    "病",
    "瘤",
    "癌",
    "综合征",
    "损伤",
    "感染",
    "障碍",
    "手术",
    "护理",
    "治疗",
    "诊断",
    "检查",
)


def _normalize_text(text: str) -> str:
    value = str(text or "")
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _is_low_quality_chunk(content: str, metadata: Dict) -> bool:
    text = _normalize_text(content)
    if len(text) < 180 or len(text) > 1400:
        return True
    page = metadata.get("page")
    if isinstance(page, int) and page < 20:
        return True
    lower = text.lower()
    if any(pattern in lower for pattern in NOISE_PATTERNS):
        return True
    zh_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_count = len(re.findall(r"[A-Za-z]", text))
    digit_count = len(re.findall(r"[0-9]", text))
    if zh_count < 140:
        return True
    if latin_count > 60 or digit_count > 50:
        return True
    if metadata.get("section") and any(tag in str(metadata.get("section")).lower() for tag in ("nav", "notice")):
        return True
    if len(re.findall(r"[。；：]", text)) < 1 and len(re.findall(r"[，,]", text)) < 3:
        return True
    if len(re.findall(r"\b\d{2,3}\b", text)) > 8:
        return True
    return False


def _extract_primary_topic(content: str) -> str:
    prefix = _normalize_text(content)[:120]
    prefix = re.sub(r"^第[一二三四五六七八九十百千0-9]+[章节篇部分卷]\s*", "", prefix)
    candidates = re.findall(r"[\u4e00-\u9fff]{2,12}", prefix)
    normalized_candidates: List[str] = []
    for candidate in candidates:
        compact = candidate.strip()
        for suffix in TOPIC_SUFFIXES:
            pos = compact.find(suffix)
            if 1 <= pos <= 7:
                compact = compact[: pos + len(suffix)]
                break
        normalized_candidates.append(compact)

    ranked: List[tuple[int, str]] = []
    for candidate in normalized_candidates:
        if candidate in GENERIC_TERMS:
            continue
        if len(candidate) > 8 and not any(candidate.endswith(suffix) for suffix in TOPIC_SUFFIXES):
            continue
        score = len(candidate)
        if candidate.endswith(TOPIC_SUFFIXES):
            score += 5
        if any(suffix in candidate for suffix in TOPIC_SUFFIXES):
            score += 2
        ranked.append((score, candidate))
    if not ranked:
        fallback_terms = _pick_topic_terms(prefix)
        for term in fallback_terms:
            if 2 <= len(term) <= 8:
                return term
    if not ranked:
        return ""
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def _pick_topic_terms(content: str) -> List[str]:
    candidates = []
    for term in extract_query_terms(content):
        if len(term) < 2:
            continue
        if term in GENERIC_TERMS:
            continue
        if re.fullmatch(r"[0-9a-zA-Z]+", term):
            continue
        candidates.append(term)
    deduped: List[str] = []
    seen = set()
    for term in candidates:
        if term in seen:
            continue
        seen.add(term)
        deduped.append(term)
    return deduped[:6]


def _first_sentence(text: str, max_len: int = 120) -> str:
    normalized = _normalize_text(text)
    parts = re.split(r"[。；!?！？]", normalized)
    for part in parts:
        part = part.strip()
        if len(part) >= 18:
            return part[:max_len]
    return normalized[:max_len]


def _reference_answer(text: str, max_len: int = 220) -> str:
    normalized = _normalize_text(text)
    return normalized[:max_len]


def _question_templates(topic: str, terms: List[str]) -> List[str]:
    aux = terms[1] if len(terms) > 1 else "临床要点"
    return [
        f"{topic}的常见表现和处理要点是什么？",
        f"关于{topic}，诊断时需要重点关注哪些关键点？",
        f"{topic}相关的症状、鉴别和处理原则怎么理解？",
        f"如果怀疑{topic}，临床上通常会关注哪些{aux}？",
    ]


def _score_candidate(content: str, metadata: Dict) -> float:
    terms = _pick_topic_terms(content)
    score = 0.0
    score += min(len(content), 900) / 900.0
    score += min(len(terms), 5) * 0.5
    if _extract_primary_topic(content):
        score += 1.0
    if metadata.get("parent_chunk_id"):
        score += 0.4
    if metadata.get("section_index"):
        score += 0.2
    return score


def _iter_samples(per_department: int) -> Iterable[Dict]:
    chunks = process_knowledge_library(KNOWLEDGE_ROOT_DIR)
    grouped: Dict[str, List[Dict]] = defaultdict(list)

    for doc in chunks:
        metadata = dict(doc.metadata or {})
        content = _normalize_text(doc.page_content)
        if _is_low_quality_chunk(content, metadata):
            continue
        primary_topic = _extract_primary_topic(content)
        topic_terms = _pick_topic_terms(content)
        if primary_topic:
            topic_terms = [primary_topic] + [term for term in topic_terms if term != primary_topic]
        if len(topic_terms) < 2:
            continue
        grouped[str(metadata.get("department") or "unknown")].append(
            {
                "content": content,
                "metadata": metadata,
                "topic_terms": topic_terms,
                "score": _score_candidate(content, metadata),
            }
        )

    for department, candidates in grouped.items():
        candidates.sort(key=lambda item: item["score"], reverse=True)
        picked = []
        seen_anchors = set()
        stride = max(1, len(candidates) // max(1, per_department * 3))
        for idx, candidate in enumerate(candidates[::stride]):
            metadata = candidate["metadata"]
            topic_terms = candidate["topic_terms"]
            topic = topic_terms[0]
            anchor_text = _first_sentence(candidate["content"], max_len=80)
            if topic in seen_anchors or len(anchor_text) < 20:
                continue
            seen_anchors.add(topic)

            template_list = _question_templates(topic, topic_terms)
            question = template_list[idx % len(template_list)]
            picked.append(
                {
                    "id": f"{department}_{len(picked) + 1:03d}",
                    "question": question,
                    "selected_department": department,
                    "expected_department": department,
                    "expected_source_book": metadata.get("source_book", ""),
                    "expected_anchor_text": anchor_text,
                    "expected_keywords": topic_terms[:3],
                    "reference_answer": _reference_answer(candidate["content"]),
                    "source_path": metadata.get("source_path", ""),
                    "source_book": metadata.get("source_book", ""),
                    "page": metadata.get("page"),
                    "department_display_name": department_display_name(department),
                    "dataset_source": "document_seed",
                }
            )
            if len(picked) >= per_department:
                break
        for item in picked:
            yield item


def build_dataset(output_path: Path, per_department: int) -> int:
    rows = list(_iter_samples(per_department=per_department))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build document-based RAG eval dataset.")
    parser.add_argument(
        "--output",
        type=str,
        default=str(BACKEND_ROOT / "data" / "eval" / "rag_eval_dataset_v1.jsonl"),
        help="Output JSONL path.",
    )
    parser.add_argument(
        "--per-department",
        type=int,
        default=12,
        help="Number of samples to keep per department.",
    )
    args = parser.parse_args()

    count = build_dataset(
        output_path=Path(args.output),
        per_department=max(1, int(args.per_department)),
    )
    print(json.dumps({"output": args.output, "samples": count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
