#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
从智能健康平台拉取最新 ECG 数据并转换为可供 LLM 生成报告的 JSON/JSONL。

流程:
1) 自动登录（验证码 OCR）
2) 查询最新一条患者心电记录（user/doctorlist）
3) 下载对应 XLS（user/data/output）
4) 解析 XLS 导联信号并计算基础特征
5) 生成与 generated_reports_*.jsonl 兼容的记录结构
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin

import numpy as np
import requests
import xlrd
from scipy.signal import find_peaks


SCP_CN_MAP = {
    "NORM": "正常心电图",
    "SR": "窦性心律",
    "SBRAD": "窦性心动过缓",
    "STACH": "窦性心动过速",
    "AFIB": "心房颤动",
    "AFLT": "心房扑动",
    "PVC": "室性早搏",
    "1AVB": "一度房室传导阻滞",
    "LBBB": "左束支传导阻滞",
    "RBBB": "右束支传导阻滞",
    "IVCD": "室内传导阻滞",
    "LVH": "左心室肥厚",
    "RVH": "右心室肥厚",
    "NDT": "非特异性T波改变",
}


class FetchError(RuntimeError):
    pass


@dataclass
class LoginConfig:
    base_url: str
    username: str
    password: str
    timeout_sec: int = 15
    max_login_attempts: int = 80


def _now_str() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _safe_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")


def _parse_signal_list(value: object) -> List[float]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    data: List[float] = []
    for token in text.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            data.append(float(token))
        except ValueError:
            continue
    return data


def _coerce_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except Exception:
        return None


def _normalize_positive_int(value: Optional[int]) -> Optional[int]:
    if value is None:
        return None
    return value if value > 0 else None


def _clean_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _dedup_keep_order(items: List[str]) -> List[str]:
    seen = set()
    out = []
    for item in items:
        if item and item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _parse_diagnosis(annotation: str) -> Tuple[List[str], List[str]]:
    annotation = (annotation or "").strip()
    if not annotation:
        return [], []

    tokens = [
        token.strip()
        for token in re.split(r"[，,；;、|/]+", annotation)
        if token.strip()
    ]

    diagnosis_codes: List[str] = []
    diagnosis_cn: List[str] = []

    for token in tokens:
        bracket_match = re.match(r"^(.*?)\s*[（(]([A-Za-z0-9_./-]+)[)）]\s*$", token)
        if bracket_match:
            cn_name = bracket_match.group(1).strip()
            code = bracket_match.group(2).strip().upper()
            if code:
                diagnosis_codes.append(code)
            if cn_name:
                diagnosis_cn.append(cn_name)
            elif code in SCP_CN_MAP:
                diagnosis_cn.append(SCP_CN_MAP[code])
            continue

        code_match = re.fullmatch(r"[A-Za-z0-9_./-]+", token)
        if code_match:
            code = token.upper()
            diagnosis_codes.append(code)
            diagnosis_cn.append(SCP_CN_MAP.get(code, code))
        else:
            diagnosis_cn.append(token)

    return _dedup_keep_order(diagnosis_codes), _dedup_keep_order(diagnosis_cn)


def _moving_average(arr: np.ndarray, window: int) -> np.ndarray:
    window = max(1, int(window))
    kernel = np.ones(window, dtype=float) / window
    return np.convolve(arr, kernel, mode="same")


def _estimate_heart_rate(signal: List[float], fs: int) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
    if not signal or len(signal) < max(30, fs // 2):
        return None, None, None, 0

    arr = np.asarray(signal, dtype=float)
    arr = arr - np.median(arr)

    baseline = _moving_average(arr, max(5, int(fs * 0.6)))
    filtered = arr - baseline
    envelope = np.abs(filtered)
    envelope = _moving_average(envelope, max(3, int(fs * 0.04)))

    threshold = max(float(np.percentile(envelope, 93) * 0.45), float(np.std(envelope) * 1.2))
    min_distance = max(1, int(fs * 0.25))
    prominence = max(1e-6, float(np.std(envelope) * 0.25))
    peaks, _ = find_peaks(envelope, height=threshold, distance=min_distance, prominence=prominence)

    if peaks.size < 2:
        return None, None, None, int(peaks.size)

    rr = np.diff(peaks) / float(fs)
    rr = rr[(rr >= 0.30) & (rr <= 2.00)]
    if rr.size == 0:
        return None, None, None, int(peaks.size)

    hr = float(60.0 / np.median(rr))
    rr_ms_mean = float(np.mean(rr) * 1000.0)
    rr_ms_std = float(np.std(rr) * 1000.0)
    if hr < 20 or hr > 260:
        return None, rr_ms_mean, rr_ms_std, int(peaks.size)
    return hr, rr_ms_mean, rr_ms_std, int(peaks.size)


def _quality_metrics(signal: List[float], fs: int) -> Tuple[Optional[float], Optional[float], Optional[float], str]:
    if not signal or len(signal) < max(30, fs // 2):
        return None, None, None, "信号缺失或长度不足"

    arr = np.asarray(signal, dtype=float)
    arr = arr - np.median(arr)
    if float(np.std(arr)) < 1e-8:
        return 0.0, 1.0, 0.0, "疑似平直信号"

    baseline = _moving_average(arr, max(5, int(fs * 0.8)))
    hp = arr - baseline
    noise_ratio = float(np.std(hp) / (np.std(arr) + 1e-8))
    baseline_wander_ratio = float(np.std(baseline) / (np.std(arr) + 1e-8))

    score = float(np.clip(1.2 - 0.8 * noise_ratio - 0.6 * baseline_wander_ratio, 0.0, 1.0))
    if score >= 0.75:
        quality_text = "质量良好"
    elif score >= 0.45:
        quality_text = "存在噪声干扰"
    else:
        quality_text = "信号质量较差"
    return score, noise_ratio, baseline_wander_ratio, quality_text


def _build_prompt(
    patient_info: Dict[str, object],
    metadata: Dict[str, object],
    features: Dict[str, object],
    signal_quality: str,
) -> str:
    age = patient_info.get("age")
    gender = patient_info.get("gender") or "待补充"
    patient_id = patient_info.get("patient_id") or "N/A"
    create_time = patient_info.get("checkup_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    heart_rate = features.get("heart_rate")
    if isinstance(heart_rate, (int, float)):
        hr_value = int(round(float(heart_rate)))
        if hr_value < 60:
            hr_text = f"{hr_value} bpm -> [偏低]"
        elif hr_value > 100:
            hr_text = f"{hr_value} bpm -> [偏高]"
        else:
            hr_text = f"{hr_value} bpm -> [正常]"
    else:
        hr_text = "[无法计算]"

    axis_degree = features.get("axis_degree")
    axis_desc = features.get("axis_desc") or ""
    axis_text = f"{axis_degree}° ({axis_desc})" if axis_degree is not None and axis_desc else "无法计算"

    diagnosis_codes = metadata.get("diagnosis_codes") or []
    diagnosis_cn = metadata.get("diagnosis_cn") or []
    diagnosis_text = []
    for idx, cn_name in enumerate(diagnosis_cn):
        code = diagnosis_codes[idx] if idx < len(diagnosis_codes) else ""
        if code and cn_name and code != cn_name:
            diagnosis_text.append(f"{cn_name} ({code})")
        elif cn_name:
            diagnosis_text.append(cn_name)
    diagnosis_line = "、".join(_dedup_keep_order(diagnosis_text)) if diagnosis_text else "待诊断"

    age_text = f"{age}岁" if isinstance(age, int) else "待补充"

    return f"""【心电图诊断报告生成任务】

===========================================================
一、患者基本信息
===========================================================
病历号: {patient_id}
年龄: {age_text} | 性别: {gender}
检查日期: {create_time}

===========================================================
二、输入特征与诊断结论
===========================================================
【算法预判诊断】:
  {diagnosis_line}

【定量测量参数】:
  - 心率: {hr_text}
  - 心电轴: {axis_text}

【信号质量】:
  {signal_quality}

===========================================================
三、指令
===========================================================
请扮演资深心电图医生，根据上述数据书写一份专业的中文诊断报告。

要求：
1. **综合分析**：不要机械翻译数据，要结合年龄、性别和数值进行综合判断。
2. **结构规范**：包含「临床信息」、「心电图所见」、「诊断结论」、「建议」四部分。
3. **特别注意**：
    - **严禁**生成“报告医师”、“审核医师”、“报告日期”、“医疗机构”等结尾签名栏或行政信息。
    - **严禁**使用 [ ] 占位符（如 [您的姓名]、[签字日期] 等）。
    - 报告请在“建议”部分结束后立即停止，不要有任何额外的结束语。
"""


class ECGWebClient:
    def __init__(self, config: LoginConfig):
        self.cfg = config
        self.session = requests.Session()
        self.base_url = config.base_url.rstrip("/") + "/"
        self._ocr = self._init_ocr()

    @staticmethod
    def _init_ocr():
        try:
            import ddddocr  # type: ignore
        except Exception as exc:
            raise FetchError(
                "缺少 ddddocr 依赖，先执行: pip install ddddocr==1.5.6"
            ) from exc
        return ddddocr.DdddOcr(show_ad=False)

    def _url(self, path: str) -> str:
        return urljoin(self.base_url, path.lstrip("/"))

    def login(self) -> None:
        last_msg = "unknown"
        for attempt in range(1, self.cfg.max_login_attempts + 1):
            try:
                self.session.get(self._url("login"), timeout=self.cfg.timeout_sec)
                cap_resp = self.session.get(
                    self._url(f"images/captcha?data={int(time.time() * 1000)}"),
                    timeout=self.cfg.timeout_sec,
                )
                if cap_resp.status_code != 200:
                    continue
                if "image" not in (cap_resp.headers.get("Content-Type") or "").lower():
                    continue
                try:
                    verify_code = self._ocr.classification(cap_resp.content)
                except Exception:
                    continue
                verify_code = (verify_code or "").strip()
                if len(verify_code) < 3:
                    continue

                login_resp = self.session.post(
                    self._url("login"),
                    data={
                        "username": self.cfg.username,
                        "password": self.cfg.password,
                        "verifyCode": verify_code,
                    },
                    timeout=self.cfg.timeout_sec,
                )
                payload = login_resp.json()
                if payload.get("code") == 200:
                    print(f"[ok] 登录成功 (attempt={attempt}, verify={verify_code})")
                    return
                last_msg = str(payload.get("message") or payload)
            except Exception as exc:
                last_msg = str(exc)

            if attempt % 10 == 0:
                print(f"[warn] 登录重试 {attempt}/{self.cfg.max_login_attempts} ...")
            time.sleep(0.05)

        raise FetchError(f"登录失败: {last_msg}")

    def get_latest_row(self) -> Dict[str, object]:
        rows = self.get_rows(page_num=1, page_size=1)
        if not rows:
            raise FetchError("doctorlist 返回为空，无法获取最新 ECG 记录")
        return rows[0]

    def get_rows(self, page_num: int = 1, page_size: int = 20) -> List[Dict[str, object]]:
        params = {
            "pageNum": page_num,
            "pageSize": page_size,
            "field": "createTime",
            "order": "desc",
            "invalidate_ie_cache": int(time.time() * 1000),
        }
        resp = self.session.get(
            self._url("user/doctorlist"),
            params=params,
            timeout=self.cfg.timeout_sec,
        )
        payload = resp.json()
        rows = (payload.get("data") or {}).get("rows") or []
        return [dict(row) for row in rows]

    def get_row_by_create_time(
        self,
        target_create_time: str,
        *,
        max_pages: int = 10,
        page_size: int = 20,
    ) -> Dict[str, object]:
        target = (target_create_time or "").strip()
        if not target:
            raise FetchError("target_create_time 不能为空")

        for page_num in range(1, max_pages + 1):
            rows = self.get_rows(page_num=page_num, page_size=page_size)
            if not rows:
                break
            for row in rows:
                if str(row.get("createTime") or "").strip() == target:
                    return row

        raise FetchError(f"未找到 createTime={target} 的 ECG 记录")

    def download_latest_xls(self, row: Dict[str, object], output_dir: Path) -> Path:
        username = str(row.get("username") or "").strip()
        create_time = str(row.get("createTime") or "").strip()
        if not username or not create_time:
            raise FetchError(f"最新记录缺少关键字段: {row}")

        resp = self.session.get(
            self._url("user/data/output"),
            params={"username": username, "createTime": create_time},
            timeout=max(30, self.cfg.timeout_sec),
        )
        if resp.status_code != 200:
            raise FetchError(f"下载 XLS 失败, status={resp.status_code}")

        content = resp.content
        if not content or content[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise FetchError("下载内容不是有效 XLS(OLE) 文件")

        cd = resp.headers.get("Content-Disposition") or ""
        m = re.search(r'filename="?([^\";]+)"?', cd)
        remote_name = m.group(1) if m else "ecg_latest.xls"

        ts = create_time.replace("-", "").replace(":", "").replace(" ", "_")
        local_name = _safe_filename(f"{Path(remote_name).stem}_{username}_{ts}.xls")
        if not local_name.endswith(".xls"):
            local_name += ".xls"

        output_dir.mkdir(parents=True, exist_ok=True)
        xls_path = output_dir / local_name
        xls_path.write_bytes(content)
        return xls_path


def parse_xls_file(xls_path: Path) -> Dict[str, object]:
    wb = xlrd.open_workbook(str(xls_path))
    sh = wb.sheet_by_index(0)
    if sh.nrows < 2:
        raise FetchError(f"XLS 数据不足: {xls_path}")

    headers = [str(sh.cell_value(0, c)).strip() for c in range(sh.ncols)]
    values = [sh.cell_value(1, c) for c in range(sh.ncols)]
    row_map = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}

    leads: Dict[str, List[float]] = {}
    for i in range(1, 13):
        key = f"导联{i}"
        leads[f"Lead_{i}"] = _parse_signal_list(row_map.get(key))

    return {
        "patient_name": str(row_map.get("患者姓名") or "").strip(),
        "patient_age": _coerce_int(row_map.get("患者年龄")),
        "doctor_name": str(row_map.get("标注医生") or "").strip(),
        "annotation": str(row_map.get("整体标注信息") or "").strip(),
        "leads": leads,
    }


def build_record(
    latest_row: Dict[str, object],
    parsed_xls: Dict[str, object],
    xls_path: Path,
    sample_rate_hz: int,
) -> Dict[str, object]:
    leads = parsed_xls["leads"]
    lead2 = leads.get("Lead_2") or leads.get("Lead_11") or leads.get("Lead_1") or []
    lead_lengths = [len(v) for v in leads.values() if v]
    sample_count = int(np.median(lead_lengths)) if lead_lengths else 0
    duration_sec = round(sample_count / float(sample_rate_hz), 3) if sample_count else None

    heart_rate, rr_mean_ms, rr_std_ms, peak_count = _estimate_heart_rate(lead2, sample_rate_hz)
    quality_score, noise_ratio, baseline_wander_ratio, quality_text = _quality_metrics(
        lead2 if lead2 else (leads.get("Lead_1") or []), sample_rate_hz
    )
    diagnosis_codes, diagnosis_cn = _parse_diagnosis(str(parsed_xls.get("annotation") or ""))

    patient_id = _coerce_int(latest_row.get("userId"))
    username = str(latest_row.get("username") or "")
    create_time = str(latest_row.get("createTime") or "")
    ecg_id_seed = f"{username}_{create_time}"
    ecg_id = int(hashlib.sha1(ecg_id_seed.encode("utf-8")).hexdigest()[:8], 16)

    ssex = str(latest_row.get("ssex") or "").strip()
    if ssex in {"1", "男", "male", "m", "男性"}:
        gender: Optional[str] = "男性"
    elif ssex in {"2", "女", "female", "f", "女性"}:
        gender = "女性"
    else:
        gender = None

    age = _normalize_positive_int(_coerce_int(parsed_xls.get("patient_age")))
    if age is None:
        age = _normalize_positive_int(_coerce_int(latest_row.get("age")))

    height = _normalize_positive_int(_coerce_int(latest_row.get("height")))
    weight = _normalize_positive_int(_coerce_int(latest_row.get("weight")))
    patient_name = _clean_text(parsed_xls.get("patient_name")) or _clean_text(latest_row.get("email"))

    metadata = {
        "patient_id": patient_id,
        "diagnosis_codes": diagnosis_codes,
        "diagnosis_cn": diagnosis_cn,
    }

    patient_info = {
        "patient_id": patient_id,
        "patient_name": patient_name,
        "age": age,
        "gender": gender,
        "height_cm": height,
        "weight_kg": weight,
        "checkup_time": create_time or None,
    }

    manual_input_required: List[str] = []
    if not patient_info["patient_name"]:
        manual_input_required.append("patient_name")
    if patient_info["age"] is None:
        manual_input_required.append("age")
    if not patient_info["gender"]:
        manual_input_required.append("gender")
    if patient_info["height_cm"] is None:
        manual_input_required.append("height_cm")
    if patient_info["weight_kg"] is None:
        manual_input_required.append("weight_kg")

    features = {
        "heart_rate": round(float(heart_rate), 2) if heart_rate is not None else None,
        "axis_degree": None,
        "axis_desc": None,
        "rr_interval_ms_mean": round(float(rr_mean_ms), 2) if rr_mean_ms is not None else None,
        "rr_interval_ms_std": round(float(rr_std_ms), 2) if rr_std_ms is not None else None,
        "pr_interval_ms": None,
        "qrs_duration_ms": None,
        "qt_interval_ms": None,
        "qtc_ms": None,
        "st_deviation_mv": None,
        "p_wave_duration_ms": None,
        "t_wave_duration_ms": None,
        "rhythm_type": None,
        "arrhythmia_flags": [],
        "r_peak_count": peak_count,
        "sample_rate_hz": sample_rate_hz,
        "sample_count": sample_count,
        "duration_sec": duration_sec,
        "signal_quality_score": round(float(quality_score), 4) if quality_score is not None else None,
        "noise_ratio": round(float(noise_ratio), 4) if noise_ratio is not None else None,
        "baseline_wander_ratio": round(float(baseline_wander_ratio), 4)
        if baseline_wander_ratio is not None
        else None,
        "signal_quality": quality_text,
    }

    skill_request = {
        "patient_info": {
            "patient_id": patient_info["patient_id"],
            "age": patient_info["age"],
            "gender": patient_info["gender"],
            "height_cm": patient_info["height_cm"],
            "weight_kg": patient_info["weight_kg"],
            "checkup_time": patient_info["checkup_time"],
        },
        "diagnosis_codes": diagnosis_codes,
        "diagnosis_cn": diagnosis_cn,
        "signal_quality": quality_text,
        "features": features,
        "notes": (
            "以下基础信息缺失，建议用户补充后再生成最终报告: "
            + ", ".join(manual_input_required)
            if manual_input_required
            else None
        ),
    }

    prompt = _build_prompt(patient_info, metadata, features, quality_text)

    return {
        "ecg_id": ecg_id,
        "metadata": metadata,
        "patient_info": patient_info,
        "features": features,
        "skill_request": skill_request,
        "manual_input_required": manual_input_required,
        "source_xls": str(xls_path),
        "source_row": {
            "username": username,
            "create_time": create_time,
            "doctor_name": _clean_text(parsed_xls.get("doctor_name")),
            "raw_annotation": _clean_text(parsed_xls.get("annotation")),
        },
        "prompt": prompt,
        "generated_report": None,
        "generation_time": None,
        "error": None,
    }


def save_outputs(
    record: Dict[str, object],
    output_dir: Path,
    xls_path: Path,
    write_jsonl: bool,
) -> Tuple[Path, Path, Optional[Path]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = xls_path.stem
    json_path = output_dir / f"{stem}.json"
    fillable_path = output_dir / f"{stem}_manual_input_template.json"
    jsonl_path: Optional[Path] = None

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    fillable_payload = {
        "patient_info": record.get("patient_info"),
        "manual_input_required": record.get("manual_input_required"),
        "tips": "请补充缺失基础信息，然后将 patient_info 回写到主 JSON 或 skill_request 中。",
    }
    with open(fillable_path, "w", encoding="utf-8") as f:
        json.dump(fillable_payload, f, ensure_ascii=False, indent=2)

    if write_jsonl:
        jsonl_path = output_dir / f"generated_reports_{_now_str()}.jsonl"
        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return json_path, fillable_path, jsonl_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="自动拉取最新 ECG XLS 并转换为 LLM 报告输入 JSON/JSONL",
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("ECG_SITE_URL", "http://124.220.204.12:8080"),
        help="站点根地址",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("ECG_SITE_USER", "doctor"),
        help="登录用户名",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("ECG_SITE_PASS", "123456"),
        help="登录密码",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).resolve().parent / "ECGdata"),
        help="下载与输出目录",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=500,
        help="采样率 Hz（用于心率估算）",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP 超时秒数",
    )
    parser.add_argument(
        "--max-login-attempts",
        type=int,
        default=80,
        help="验证码登录最大尝试次数",
    )
    parser.add_argument(
        "--write-jsonl",
        action="store_true",
        help="额外输出一份 JSONL（单行记录，机器读取用）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    cfg = LoginConfig(
        base_url=args.base_url,
        username=args.username,
        password=args.password,
        timeout_sec=args.timeout,
        max_login_attempts=args.max_login_attempts,
    )
    client = ECGWebClient(cfg)

    print("[1/5] 登录站点...")
    client.login()

    print("[2/5] 获取最新 ECG 记录...")
    latest_row = client.get_latest_row()
    print(
        f"      latest: username={latest_row.get('username')} "
        f"createTime={latest_row.get('createTime')}"
    )

    print("[3/5] 下载最新 XLS ...")
    xls_path = client.download_latest_xls(latest_row, output_dir)
    print(f"      saved xls: {xls_path}")

    print("[4/5] 解析 XLS 并计算特征...")
    parsed_xls = parse_xls_file(xls_path)
    record = build_record(latest_row, parsed_xls, xls_path, sample_rate_hz=args.sample_rate)

    print("[5/5] 写入 JSON ...")
    json_path, fillable_path, jsonl_path = save_outputs(
        record,
        output_dir,
        xls_path,
        write_jsonl=args.write_jsonl,
    )
    print(f"      json : {json_path}")
    print(f"      fill : {fillable_path}")
    if jsonl_path is not None:
        print(f"      jsonl: {jsonl_path}")
    print("✅ 完成")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"❌ 执行失败: {exc}")
        sys.exit(1)
