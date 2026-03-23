"""
MediGenius — services/flow_trace_service.py
Append chat flow-trace records to docs for manual review.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from app.core.logging_config import logger

REPO_ROOT = Path(__file__).resolve().parents[3]
TRACE_DOC_PATH = REPO_ROOT / "docs" / "flow-trace-record.md"
TRACE_JSONL_PATH = REPO_ROOT / "docs" / "flow-trace-record.jsonl"


def _escape_table_cell(value: str) -> str:
    return (value or "").replace("|", "\\|").replace("\n", "<br>")


def _render_notes(
    safety_level: str,
    domain: str,
    use_rag: bool,
    need_rag: bool,
    primary_department: str,
    profiling: dict | None = None,
) -> str:
    parts = [
        f"safety_level={safety_level}",
        f"domain={domain}",
        f"primary_department={primary_department}",
        f"use_rag={use_rag}",
        f"need_rag={need_rag}",
    ]
    if profiling and isinstance(profiling, dict):
        node_timings = profiling.get("node_timings_ms") or {}
        if isinstance(node_timings, dict) and node_timings:
            total_ms = round(sum(float(v) for v in node_timings.values()), 2)
            parts.append(f"node_total_ms={total_ms}")
        token_usage = profiling.get("token_usage") or {}
        if isinstance(token_usage, dict) and token_usage:
            parts.append(f"tokens={int(token_usage.get('total_tokens', 0))}")
    return ", ".join(parts)


def append_flow_trace_record(
    session_id: str,
    question: str,
    flow_trace: Iterable[str],
    source: str,
    safety_level: str,
    domain: str,
    primary_department: str,
    use_rag: bool,
    need_rag: bool,
    profiling: dict[str, Any] | None = None,
) -> None:
    """Append one trace record to markdown and JSONL docs."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    flow_trace_list = list(flow_trace)
    notes = _render_notes(
        safety_level,
        domain,
        use_rag,
        need_rag,
        primary_department,
        profiling=profiling,
    )

    record = {
        "timestamp": timestamp,
        "session_id": session_id,
        "question": question,
        "flow_trace": flow_trace_list,
        "source": source,
        "notes": notes,
        "profiling": profiling or {},
    }

    try:
        TRACE_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        with TRACE_JSONL_PATH.open("a", encoding="utf-8") as jsonl_file:
            jsonl_file.write(json.dumps(record, ensure_ascii=False) + "\n")

        markdown_row = (
            f"| {_escape_table_cell(timestamp)} "
            f"| {_escape_table_cell(session_id)} "
            f"| {_escape_table_cell(question)} "
            f"| `{json.dumps(flow_trace_list, ensure_ascii=False)}` "
            f"| {_escape_table_cell(source)} "
            f"| {_escape_table_cell(notes)} |\n"
        )
        with TRACE_DOC_PATH.open("a", encoding="utf-8") as markdown_file:
            markdown_file.write(markdown_row)
    except Exception as exc:
        logger.warning("Flow trace record append failed: %s", exc)
