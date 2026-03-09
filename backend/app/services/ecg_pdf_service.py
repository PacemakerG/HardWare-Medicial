"""
MediGenius — services/ecg_pdf_service.py
Generate ECG PDF report (Phase 1):
- Lead II waveform figure
- Structured text report sections
"""

from __future__ import annotations

import io
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List

from app.core.config import ECG_REPORT_PDF_DIR
from app.core.logging_config import logger


def get_report_pdf_path(report_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", str(report_id or "")).strip("_")
    if not safe_id:
        safe_id = "unknown"
    return Path(ECG_REPORT_PDF_DIR) / f"{safe_id}.pdf"


def _strip_markdown(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"`([^`]*)`", r"\1", text)
    cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"^#+\s*", "", cleaned, flags=re.MULTILINE)
    return cleaned


def _pick_lead_ii(waveform: Dict[str, List[float]]) -> List[float]:
    if not waveform:
        return []
    candidate_keys = ("lead_ii", "Lead_2", "II", "lead2", "leadII")
    for key in candidate_keys:
        values = waveform.get(key)
        if isinstance(values, list) and values:
            return [float(v) for v in values if isinstance(v, (int, float))]
    for values in waveform.values():
        if isinstance(values, list) and values:
            return [float(v) for v in values if isinstance(v, (int, float))]
    return []


def _build_waveform_png(lead_signal: List[float], sample_rate_hz: int) -> bytes | None:
    if not lead_signal:
        return None

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except Exception as exc:
        logger.warning("PDF waveform plotting dependency missing: %s", exc)
        return None

    signal = lead_signal[:5000]
    x = np.arange(len(signal), dtype=float) / float(max(sample_rate_hz, 1))

    fig, ax = plt.subplots(figsize=(9.2, 2.4), dpi=170)
    ax.plot(x, signal, color="#1f2937", linewidth=1.0)
    ax.set_title("Lead II ECG Waveform", fontsize=10)
    ax.set_xlabel("Time (s)", fontsize=8)
    ax.set_ylabel("Amplitude", fontsize=8)
    ax.tick_params(axis="both", labelsize=7)
    ax.minorticks_on()
    ax.grid(which="major", color="#f4b3b3", linewidth=0.6)
    ax.grid(which="minor", color="#f9d8d8", linewidth=0.3)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()


def _draw_text_block(
    c,
    text_lines: Iterable[str],
    *,
    x: float,
    y: float,
    max_width: float,
    page_height: float,
    font_name: str,
    font_size: int = 10,
    line_height: int = 14,
) -> float:
    from reportlab.lib.utils import simpleSplit

    c.setFont(font_name, font_size)
    current_y = y
    for line in text_lines:
        wrapped = simpleSplit(str(line), font_name, font_size, max_width) or [""]
        for seg in wrapped:
            if current_y < 60:
                c.showPage()
                c.setFont(font_name, font_size)
                current_y = page_height - 50
            c.drawString(x, current_y, seg)
            current_y -= line_height
    return current_y


def generate_ecg_pdf(
    *,
    report_id: str,
    created_at: str,
    patient_info: Dict,
    features: Dict,
    waveform: Dict[str, List[float]],
    report_text: str,
    risk_level: str,
    key_findings: List[str],
    recommendations: List[str],
    disclaimer: str,
) -> str | None:
    """
    Generate ECG PDF and return absolute file path.
    Returns None if dependency missing or generation failed.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except Exception as exc:
        logger.warning("PDF dependency missing, skip PDF generation: %s", exc)
        return None

    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        font_name = "STSong-Light"
    except Exception:
        font_name = "Helvetica"

    sample_rate = int(features.get("sample_rate_hz") or 500)
    waveform_png = _build_waveform_png(_pick_lead_ii(waveform), sample_rate)

    pdf_path = get_report_pdf_path(report_id)
    os.makedirs(pdf_path.parent, exist_ok=True)

    page_width, page_height = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    left = 40
    content_width = page_width - 80

    c.setFont(font_name, 16)
    c.drawString(left, page_height - 40, "ECG 专家分析报告")
    c.setFont(font_name, 10)
    c.drawString(left, page_height - 58, f"报告ID: {report_id}")
    c.drawString(left + 240, page_height - 58, f"生成时间: {created_at or '未知'}")
    c.drawString(left, page_height - 74, f"风险等级: {risk_level}")

    patient_lines = [
        "患者信息",
        f"姓名: {patient_info.get('patient_name') or '未知'}    病历号: {patient_info.get('patient_id') or '未知'}",
        (
            f"年龄: {patient_info.get('age') if patient_info.get('age') is not None else '未知'}"
            f"    性别: {patient_info.get('gender') or '未知'}"
            f"    身高: {patient_info.get('height_cm') or '未知'} cm"
            f"    体重: {patient_info.get('weight_kg') or '未知'} kg"
        ),
        f"检查时间: {patient_info.get('checkup_time') or '未知'}",
    ]
    y = _draw_text_block(
        c,
        patient_lines,
        x=left,
        y=page_height - 96,
        max_width=content_width,
        page_height=page_height,
        font_name=font_name,
        font_size=10,
    )

    if waveform_png:
        img = ImageReader(io.BytesIO(waveform_png))
        img_h = 170
        y_img = y - img_h - 8
        if y_img < 80:
            c.showPage()
            y_img = page_height - 240
        c.setFont(font_name, 11)
        c.drawString(left, y_img + img_h + 8, "ECG 波形（Lead II）")
        c.drawImage(img, left, y_img, width=content_width, height=img_h, preserveAspectRatio=True)
        y = y_img - 14
    else:
        y = _draw_text_block(
            c,
            ["ECG 波形（Lead II）", "波形数据不可用或绘图依赖缺失。"],
            x=left,
            y=y - 8,
            max_width=content_width,
            page_height=page_height,
            font_name=font_name,
            font_size=10,
        )

    report_lines = ["文字报告"] + _strip_markdown(report_text).splitlines()
    y = _draw_text_block(
        c,
        report_lines,
        x=left,
        y=y,
        max_width=content_width,
        page_height=page_height,
        font_name=font_name,
        font_size=10,
    )
    y = _draw_text_block(
        c,
        ["关键发现"] + [f"- {x}" for x in key_findings],
        x=left,
        y=y - 8,
        max_width=content_width,
        page_height=page_height,
        font_name=font_name,
        font_size=10,
    )
    y = _draw_text_block(
        c,
        ["建议"] + [f"- {x}" for x in recommendations] + [f"免责声明: {disclaimer}"],
        x=left,
        y=y - 8,
        max_width=content_width,
        page_height=page_height,
        font_name=font_name,
        font_size=10,
    )

    c.save()
    return str(pdf_path)

