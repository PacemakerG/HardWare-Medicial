"""
MediGenius — services/ecg_report_service.py
ECG report generation skill service.
"""

import os
from typing import Any, Dict, List

from app.core.logging_config import logger
from app.schemas.ecg import ECGReportRequest, ECGReportResponse
from app.services.database_service import db_service
from app.services.ecg_pdf_service import generate_ecg_pdf, get_report_pdf_path
from app.services.profile_service import update_profile
from app.tools.llm_client import get_llm

DISCLAIMER = (
    "本报告仅供临床辅助参考，不可替代执业医师面对面诊断。"
    "如出现胸痛持续、呼吸困难、晕厥等紧急症状，请立即就医。"
)
HIGH_RISK_ALERT = "【紧急提示】当前结果提示较高风险，请尽快急诊或由心内科医生立即评估。"


def _build_pdf_url(report_id: str) -> str:
    return f"/api/v1/ecg/report/{report_id}/pdf"


def _resolve_pdf_url(report_id: str) -> str | None:
    path = get_report_pdf_path(report_id)
    return _build_pdf_url(report_id) if os.path.exists(path) else None


def _format_patient_info(data: ECGReportRequest) -> str:
    info = data.patient_info
    return (
        f"病历号: {info.patient_id or '未知'}\n"
        f"年龄: {info.age if info.age is not None else '未知'}\n"
        f"性别: {info.gender or '未知'}\n"
        f"身高: {info.height_cm if info.height_cm is not None else '未知'} cm\n"
        f"体重: {info.weight_kg if info.weight_kg is not None else '未知'} kg\n"
        f"检查时间: {info.checkup_time or '未知'}\n"
    )


def _format_features(features: Dict[str, Any]) -> str:
    if not features:
        return "无结构化参数。"
    lines = []
    for key, value in features.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)


def _infer_risk_level(data: ECGReportRequest) -> str:
    hr_raw = data.features.get("heart_rate")
    try:
        hr = float(hr_raw) if hr_raw is not None else None
    except (TypeError, ValueError):
        hr = None

    high_risk_codes = {"AMI", "STEMI", "VF", "VT", "AFIB_RVR"}
    if any(code.upper() in high_risk_codes for code in data.diagnosis_codes):
        return "high"
    if hr is not None and (hr < 40 or hr > 130):
        return "high"
    if hr is not None and (hr < 50 or hr > 110):
        return "medium"
    if data.signal_quality and "噪声" in data.signal_quality:
        return "medium"
    return "low"


def _extract_key_findings(data: ECGReportRequest) -> List[str]:
    findings: List[str] = []
    if data.diagnosis_cn:
        findings.append("算法预判: " + "、".join(data.diagnosis_cn[:4]))
    elif data.diagnosis_codes:
        findings.append("算法预判: " + "、".join(data.diagnosis_codes[:4]))

    if "heart_rate" in data.features:
        findings.append(f"心率: {data.features.get('heart_rate')} bpm")
    if "axis_degree" in data.features:
        findings.append(f"心电轴: {data.features.get('axis_degree')}°")
    if data.signal_quality:
        findings.append(f"信号质量: {data.signal_quality}")
    return findings or ["未检测到可解释的关键异常。"]


def _build_recommendations(risk_level: str) -> List[str]:
    if risk_level == "high":
        return [
            "建议立即由心内科或急诊医生进一步评估。",
            "如伴胸痛、呼吸困难、晕厥等症状，请立即急诊处理。",
            "尽快完善动态心电图、心肌损伤标志物等检查。",
        ]
    if risk_level == "medium":
        return [
            "建议近期复查心电图，并结合症状由心内科门诊评估。",
            "若症状加重或出现胸痛、晕厥，应立即就医。",
            "可结合动态心电图进一步观察节律变化。",
        ]
    return [
        "当前结果整体风险较低，建议结合临床症状继续观察。",
        "保持规律作息、适度运动，避免熬夜和高强度刺激。",
        "如出现持续不适，建议复查心电图并就诊评估。",
    ]


def _ensure_safety_guardrail(report: str, risk_level: str) -> str:
    text = (report or "").strip()
    if risk_level == "high" and "紧急" not in text and "急诊" not in text:
        text = f"{text}\n\n{HIGH_RISK_ALERT}"
    return text


def _build_profile_updates(data: ECGReportRequest, risk_level: str, report_id: str) -> Dict[str, Dict]:
    diagnosis = "、".join(data.diagnosis_cn[:3]) if data.diagnosis_cn else "、".join(data.diagnosis_codes[:3])
    heart_rate = data.features.get("heart_rate")
    axis = data.features.get("axis_degree")
    context = {
        "last_ecg_report_id": report_id,
        "last_ecg_risk_level": risk_level,
        "last_ecg_diagnosis": diagnosis or "未知",
    }
    if heart_rate is not None:
        context["last_ecg_heart_rate"] = f"{heart_rate} bpm"
    if axis is not None:
        context["last_ecg_axis_degree"] = f"{axis}°"
    return {"current_context": context}


def _fallback_report(data: ECGReportRequest, findings: List[str], recommendations: List[str]) -> str:
    return (
        "**心电图诊断报告**\n\n"
        "**临床信息**\n"
        f"{_format_patient_info(data)}\n"
        "**心电图所见**\n"
        + "\n".join(f"{idx}. {item}" for idx, item in enumerate(findings, start=1))
        + "\n\n**诊断结论**\n"
        + "请结合临床表现与进一步检查综合判断。\n\n"
        + "**建议**\n"
        + "\n".join(f"{idx}. {item}" for idx, item in enumerate(recommendations, start=1))
    )


def _build_prompt(data: ECGReportRequest) -> str:
    return (
        "【心电图诊断报告生成任务】\n\n"
        "你是一名资深心电图医生，请根据输入信息生成专业中文报告。\n"
        "报告必须包含四部分：临床信息、心电图所见、诊断结论、建议。\n"
        "禁止输出行政签名栏（报告医师/审核医师/机构/日期等）。\n"
        "禁止输出占位符。\n\n"
        "【患者基本信息】\n"
        f"{_format_patient_info(data)}\n"
        "【算法预判诊断】\n"
        f"- 诊断编码: {data.diagnosis_codes or ['未知']}\n"
        f"- 中文诊断: {data.diagnosis_cn or ['未知']}\n\n"
        "【ECG参数】\n"
        f"{_format_features(data.features)}\n\n"
        f"【信号质量】\n{data.signal_quality or '未知'}\n\n"
        f"【补充说明】\n{data.notes or '无'}\n"
    )


class ECGReportService:
    """Skill-like service for ECG report generation."""

    def generate_report(
        self,
        request: ECGReportRequest,
        session_id: str = "",
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> ECGReportResponse:
        risk_level = _infer_risk_level(request)
        key_findings = _extract_key_findings(request)
        recommendations = _build_recommendations(risk_level)

        llm = get_llm(tenant_id=tenant_id, user_id=user_id)
        report = ""
        if llm:
            prompt = _build_prompt(request)
            try:
                response = llm.invoke(prompt)
                report = (
                    response.content.strip()
                    if hasattr(response, "content")
                    else str(response).strip()
                )
            except Exception as exc:
                logger.warning("ECG report generation via LLM failed: %s", exc)

        if not report:
            report = _fallback_report(request, key_findings, recommendations)
        report = _ensure_safety_guardrail(report, risk_level)

        raw_request_payload = request.model_dump(exclude={"waveform"})
        saved = db_service.save_ecg_report(
            session_id=session_id or None,
            tenant_id=tenant_id,
            user_id=user_id,
            patient_id=request.patient_info.patient_id,
            risk_level=risk_level,
            report=report,
            key_findings=key_findings,
            recommendations=recommendations,
            disclaimer=DISCLAIMER,
            raw_request=raw_request_payload,
        )
        report_id = saved.get("report_id")
        created_at = saved.get("created_at")
        pdf_url = None

        if report_id:
            try:
                pdf_path = generate_ecg_pdf(
                    report_id=report_id,
                    created_at=created_at,
                    patient_info=request.patient_info.model_dump(),
                    features=request.features,
                    waveform=request.waveform,
                    report_text=report,
                    risk_level=risk_level,
                    key_findings=key_findings,
                    recommendations=recommendations,
                    disclaimer=DISCLAIMER,
                )
                if pdf_path and os.path.exists(pdf_path):
                    pdf_url = _build_pdf_url(report_id)
            except Exception as exc:
                logger.warning("ECG PDF generation failed: %s", exc)

        if session_id:
            try:
                update_profile(
                    session_id,
                    _build_profile_updates(request, risk_level, report_id),
                    tenant_id=tenant_id,
                    user_id=user_id,
                )
            except Exception as exc:
                logger.warning("Failed to write ECG summary into profile: %s", exc)

        return ECGReportResponse(
            report_id=report_id,
            created_at=created_at,
            report=report,
            risk_level=risk_level,
            key_findings=key_findings,
            recommendations=recommendations,
            disclaimer=DISCLAIMER,
            pdf_url=pdf_url,
            success=bool(report.strip()),
        )

    def get_report_by_id(
        self,
        report_id: str,
        *,
        tenant_id: str = "default",
        user_id: str = "anonymous",
    ) -> ECGReportResponse | None:
        record = db_service.get_ecg_report(
            report_id,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        if not record:
            return None
        return ECGReportResponse(
            report_id=record.get("report_id"),
            created_at=record.get("created_at"),
            report=record.get("report", ""),
            risk_level=record.get("risk_level", "unknown"),
            key_findings=record.get("key_findings") or [],
            recommendations=record.get("recommendations") or [],
            disclaimer=record.get("disclaimer", DISCLAIMER),
            pdf_url=(
                _resolve_pdf_url(record.get("report_id"))
                if record.get("report_id")
                else None
            ),
            success=bool((record.get("report") or "").strip()),
        )


ecg_report_service = ECGReportService()
