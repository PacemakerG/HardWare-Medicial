#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
ECG XLS 文件解析器 - 转换为 LLM-PROMPT 标准 JSONL 格式。

输出字段与 generated_reports_*.jsonl 对齐：
- ecg_id
- metadata: patient_id / diagnosis_codes / diagnosis_cn
- features: heart_rate / axis_degree / axis_desc
- prompt
- generated_report
- generation_time
- error
"""

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

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


def parse_lead_data(lead_value: object) -> List[float]:
    """解析导联字符串（逗号分隔）为浮点数组。"""
    if pd.isna(lead_value):
        return []
    if isinstance(lead_value, (int, float)):
        return [float(lead_value)]
    if not isinstance(lead_value, str):
        return []

    try:
        return [float(x.strip()) for x in lead_value.split(",") if x.strip()]
    except ValueError:
        return []


def safe_text(value: object) -> str:
    """将单元格值转为清洗后的字符串。"""
    if pd.isna(value):
        return ""
    text = str(value).strip()
    return "" if text.lower() == "nan" else text


def safe_int(value: object) -> Optional[int]:
    """将单元格值转为整数，失败返回 None。"""
    if pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def deduplicate_keep_order(items: List[str]) -> List[str]:
    """去重并保持原始顺序。"""
    seen = set()
    deduped = []
    for item in items:
        if item and item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def normalize_gender(raw_gender: str) -> str:
    """归一化性别表示。"""
    gender = raw_gender.strip().lower()
    if gender in {"1", "男", "male", "m", "男性"}:
        return "男性"
    if gender in {"2", "女", "female", "f", "女性"}:
        return "女性"
    return "未知"


def parse_record_datetime(row: pd.Series) -> str:
    """提取检查时间，缺失时使用当前时间。"""
    candidate_columns = [
        "检查日期",
        "检查时间",
        "记录时间",
        "record_date",
        "recording_date",
    ]
    for col in candidate_columns:
        if col not in row.index:
            continue
        value = row.get(col)
        if pd.isna(value):
            continue
        if isinstance(value, pd.Timestamp):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        text = safe_text(value)
        if text:
            return text

    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def build_patient_id(row: pd.Series, patient_name: str, seed_id: int) -> int:
    """优先读取病历号/患者ID，缺失时使用稳定哈希。"""
    for col in ["patient_id", "患者ID", "病历号", "病人ID"]:
        if col in row.index:
            parsed = safe_int(row.get(col))
            if parsed is not None and parsed >= 0:
                return parsed

    seed_text = f"{patient_name}_{seed_id}" if patient_name else f"anonymous_{seed_id}"
    digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100000


def parse_diagnosis(annotation: str) -> Tuple[List[str], List[str]]:
    """从整体标注信息中提取 diagnosis_codes 与 diagnosis_cn。"""
    annotation = safe_text(annotation)
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

    return (
        deduplicate_keep_order(diagnosis_codes),
        deduplicate_keep_order(diagnosis_cn),
    )


def detect_r_peaks(
    signal: List[float],
    sampling_rate: int = 500,
    min_distance_sec: float = 0.25,
) -> List[int]:
    """简单 R 波检测（基于绝对幅值局部峰 + 不应期）。"""
    if not signal or len(signal) < 3:
        return []

    arr = np.asarray(signal, dtype=float)
    arr = arr - np.median(arr)
    abs_arr = np.abs(arr)

    min_distance = max(1, int(min_distance_sec * sampling_rate))
    threshold = max(np.percentile(abs_arr, 90) * 0.55, np.std(abs_arr) * 1.2)
    if threshold <= 0:
        return []

    peaks: List[int] = []
    for idx in range(1, len(abs_arr) - 1):
        current = abs_arr[idx]
        if current < threshold:
            continue
        if current >= abs_arr[idx - 1] and current > abs_arr[idx + 1]:
            if not peaks or (idx - peaks[-1]) >= min_distance:
                peaks.append(idx)
            elif current > abs_arr[peaks[-1]]:
                peaks[-1] = idx

    return peaks


def calculate_heart_rate(
    signal: List[float],
    sampling_rate: int = 500,
) -> Optional[int]:
    """由 R-R 间期估算心率（bpm），失败返回 None。"""
    if not signal:
        return None

    r_peaks = detect_r_peaks(signal, sampling_rate=sampling_rate)
    if len(r_peaks) < 2:
        return None

    rr_intervals = np.diff(r_peaks)
    if rr_intervals.size == 0:
        return None

    avg_rr = float(np.mean(rr_intervals))
    if avg_rr <= 0:
        return None

    heart_rate = 60.0 * sampling_rate / avg_rr
    if heart_rate < 20 or heart_rate > 250:
        return None

    return int(round(heart_rate))


def calculate_axis(
    lead_i: List[float],
    lead_avf: List[float],
) -> Tuple[Optional[int], Optional[str]]:
    """使用 I + aVF 估算心电轴。"""
    if not lead_i or not lead_avf:
        return None, None

    i_arr = np.asarray(lead_i, dtype=float)
    avf_arr = np.asarray(lead_avf, dtype=float)
    if i_arr.size == 0 or avf_arr.size == 0:
        return None, None

    def _net_amplitude(arr: np.ndarray) -> float:
        pos = arr[arr > 0]
        neg = arr[arr < 0]
        pos_mean = float(np.mean(pos)) if pos.size else 0.0
        neg_mean = float(np.mean(neg)) if neg.size else 0.0
        return pos_mean + neg_mean

    net_i = _net_amplitude(i_arr)
    net_avf = _net_amplitude(avf_arr)
    angle = math.degrees(math.atan2(net_avf, net_i))
    if np.isnan(angle):
        return None, None

    angle_int = int(round(angle))
    if -30 <= angle_int <= 90:
        desc = "正常心电轴"
    elif -90 <= angle_int < -30:
        desc = "电轴左偏"
    elif 90 < angle_int <= 180:
        desc = "电轴右偏"
    else:
        desc = "极度电轴偏移"

    return angle_int, desc


def assess_heart_rate_status(heart_rate: Optional[int]) -> str:
    """给出心率状态文本。"""
    if heart_rate is None:
        return "无法计算"
    if heart_rate < 60:
        return "偏低"
    if heart_rate > 100:
        return "偏高"
    return "正常"


def evaluate_signal_quality(leads: Dict[str, List[float]]) -> str:
    """基于导联完整性和尖峰噪声给出粗略质量评估。"""
    usable = [np.asarray(values, dtype=float) for values in leads.values() if len(values) >= 20]
    if len(usable) < 6:
        return "信号缺失或不完整"

    lengths = [arr.size for arr in usable]
    median_len = float(np.median(lengths))
    if min(lengths) < 0.8 * median_len:
        return "存在噪声干扰 (导联长度不一致)"

    noisy_leads = 0
    for arr in usable:
        baseline = np.percentile(np.abs(arr - np.median(arr)), 95)
        if baseline <= 0:
            continue
        spikes = np.percentile(np.abs(np.diff(arr)), 99)
        if spikes > baseline * 3.0:
            noisy_leads += 1

    if noisy_leads >= max(2, len(usable) // 4):
        return "存在噪声干扰 (多导联尖峰干扰)"
    return "质量良好"


def format_diagnosis_for_prompt(metadata: Dict[str, Union[int, List[str]]]) -> str:
    """将 metadata 中诊断字段格式化为 prompt 展示文本。"""
    diagnosis_codes = metadata.get("diagnosis_codes", []) or []
    diagnosis_cn = metadata.get("diagnosis_cn", []) or []

    entries: List[str] = []
    for idx, cn_name in enumerate(diagnosis_cn):
        code = diagnosis_codes[idx] if idx < len(diagnosis_codes) else ""
        if code and cn_name and code != cn_name:
            entries.append(f"{cn_name} ({code})")
        elif cn_name:
            entries.append(cn_name)

    if not entries and diagnosis_codes:
        for code in diagnosis_codes:
            cn_name = SCP_CN_MAP.get(code, "")
            entries.append(f"{cn_name} ({code})" if cn_name else code)

    entries = deduplicate_keep_order(entries)
    return "、".join(entries) if entries else "待诊断"


def generate_prompt(
    patient_info: Dict[str, Union[int, str, None]],
    metadata: Dict[str, Union[int, List[str]]],
    features: Dict[str, Optional[Union[int, str]]],
    signal_quality: str,
) -> str:
    """生成与现有 LLM-PROMPT 兼容的中文 prompt。"""
    age = patient_info.get("age")
    age_text = f"{age}岁" if isinstance(age, int) and age >= 0 else "N/A"
    gender = patient_info.get("gender") or "未知"
    record_date = patient_info.get("record_date") or datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    heart_rate = features.get("heart_rate")
    if heart_rate is None:
        heart_rate_text = "[无法计算]"
    else:
        hr_status = assess_heart_rate_status(int(heart_rate))
        heart_rate_text = f"{heart_rate} bpm -> [{hr_status}]"

    axis_degree = features.get("axis_degree")
    axis_desc = features.get("axis_desc")
    if axis_degree is None or not axis_desc:
        axis_text = "无法计算"
    else:
        axis_text = f"{axis_degree}° ({axis_desc})"

    diagnosis_text = format_diagnosis_for_prompt(metadata)

    return f"""【心电图诊断报告生成任务】

===========================================================
一、患者基本信息
===========================================================
病历号: {metadata.get('patient_id', 'N/A')}
年龄: {age_text} | 性别: {gender}
检查日期: {record_date}

===========================================================
二、输入特征与诊断结论
===========================================================
【算法预判诊断】:
  {diagnosis_text}

【定量测量参数】:
  - 心率: {heart_rate_text}
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


def extract_leads_from_row(row: pd.Series) -> Dict[str, List[float]]:
    """从一行数据提取 12 导联。"""
    leads: Dict[str, List[float]] = {}
    for i in range(1, 13):
        col_name = f"导联{i}"
        leads[f"Lead_{i}"] = parse_lead_data(row.get(col_name, ""))
    return leads


def parse_row_to_record(
    row: pd.Series,
    ecg_id: int,
    sampling_rate: int = 500,
) -> Dict:
    """将单行 XLS 数据解析为标准 JSONL 记录。"""
    patient_name = safe_text(row.get("患者姓名"))
    patient_age = safe_int(row.get("患者年龄"))
    if patient_age is None and "age" in row.index:
        patient_age = safe_int(row.get("age"))

    gender_raw = safe_text(row.get("患者性别")) or safe_text(row.get("性别"))
    patient_gender = normalize_gender(gender_raw) if gender_raw else "未知"
    record_date = parse_record_datetime(row)

    annotation = safe_text(row.get("整体标注信息"))
    diagnosis_codes, diagnosis_cn = parse_diagnosis(annotation)

    patient_id = build_patient_id(row, patient_name, seed_id=ecg_id)
    metadata = {
        "patient_id": patient_id,
        "diagnosis_codes": diagnosis_codes,
        "diagnosis_cn": diagnosis_cn,
    }

    leads = extract_leads_from_row(row)
    lead_ii = leads.get("Lead_2", [])
    if not lead_ii:
        for fallback_key in ("Lead_11", "Lead_1"):
            if leads.get(fallback_key):
                lead_ii = leads[fallback_key]
                break

    lead_i = leads.get("Lead_1", [])
    lead_avf = leads.get("Lead_6", [])
    if not lead_avf:
        lead_avf = leads.get("Lead_3", [])

    heart_rate = calculate_heart_rate(lead_ii, sampling_rate=sampling_rate)
    axis_degree, axis_desc = calculate_axis(lead_i, lead_avf)

    features = {
        "heart_rate": heart_rate,
        "axis_degree": axis_degree,
        "axis_desc": axis_desc,
    }

    signal_quality = evaluate_signal_quality(leads)
    patient_info = {
        "patient_id": patient_id,
        "age": patient_age,
        "gender": patient_gender,
        "record_date": record_date,
    }
    prompt = generate_prompt(patient_info, metadata, features, signal_quality)

    return {
        "ecg_id": ecg_id,
        "metadata": metadata,
        "features": features,
        "prompt": prompt,
        "generated_report": None,
        "generation_time": datetime.now().isoformat(),
        "error": None,
    }


def parse_ecg_xls_to_prompt_records(
    file_path: Union[str, Path],
    start_ecg_id: int = 1,
    sampling_rate: int = 500,
) -> List[Dict]:
    """读取 XLS 并逐行转换为标准记录列表。"""
    input_path = Path(file_path)
    if not input_path.exists():
        raise FileNotFoundError(f"文件不存在: {input_path}")

    try:
        df = pd.read_excel(input_path, engine="xlrd")
    except Exception as exc:
        raise ValueError(f"无法读取 Excel 文件: {exc}") from exc

    if df.empty:
        raise ValueError("Excel 文件中没有有效数据")

    records: List[Dict] = []
    for offset, (_, row) in enumerate(df.iterrows()):
        ecg_id = start_ecg_id + offset
        records.append(parse_row_to_record(row, ecg_id, sampling_rate=sampling_rate))

    return records


def write_jsonl(records: List[Dict], output_path: Path) -> None:
    """写入 JSONL 文件。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_obj:
        for record in records:
            file_obj.write(json.dumps(record, ensure_ascii=False) + "\n")


def normalize_output_path(
    input_path: Path,
    output_path: Optional[Union[str, Path]],
) -> Path:
    """支持将输出参数解释为文件路径或目录路径。"""
    if output_path is None:
        return input_path.with_suffix(".jsonl")

    output = Path(output_path)
    if output.exists() and output.is_dir():
        return output / input_path.with_suffix(".jsonl").name
    if output.suffix.lower() == ".jsonl":
        return output

    output.mkdir(parents=True, exist_ok=True)
    return output / input_path.with_suffix(".jsonl").name


def convert_to_jsonl(
    input_path: Union[str, Path],
    output_path: Optional[Union[str, Path]] = None,
    start_ecg_id: int = 1,
    sampling_rate: int = 500,
) -> str:
    """将单个 XLS 文件转换为标准 JSONL。"""
    input_path = Path(input_path)
    output = normalize_output_path(input_path, output_path)

    records = parse_ecg_xls_to_prompt_records(
        input_path, start_ecg_id=start_ecg_id, sampling_rate=sampling_rate
    )
    write_jsonl(records, output)

    print("✅ 转换完成!")
    print(f"   输入: {input_path}")
    print(f"   输出: {output}")
    print(f"   记录数: {len(records)}")
    print(f"   起始 ECG ID: {start_ecg_id}")

    if records:
        first = records[0]
        print(f"   首条心率: {first['features']['heart_rate']}")
        print(f"   首条心电轴: {first['features']['axis_degree']} / {first['features']['axis_desc']}")

    return str(output)


def batch_convert(
    input_dir: Union[str, Path],
    output_dir: Optional[Union[str, Path]] = None,
    pattern: str = "*.xls",
    start_ecg_id: int = 1,
    sampling_rate: int = 500,
) -> List[str]:
    """批量转换目录下所有 XLS 文件。"""
    input_dir = Path(input_dir)
    if output_dir is None:
        output_dir = input_dir
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    xls_files = sorted(input_dir.glob(pattern))
    if not xls_files:
        print(f"未找到匹配 {pattern} 的文件")
        return []

    current_ecg_id = start_ecg_id
    outputs: List[str] = []
    print(f"找到 {len(xls_files)} 个文件，开始转换...\n")

    for index, xls_file in enumerate(xls_files, 1):
        print(f"[{index}/{len(xls_files)}] 处理: {xls_file.name}")
        try:
            records = parse_ecg_xls_to_prompt_records(
                xls_file,
                start_ecg_id=current_ecg_id,
                sampling_rate=sampling_rate,
            )
            out_file = output_dir / xls_file.with_suffix(".jsonl").name
            write_jsonl(records, out_file)
            outputs.append(str(out_file))
            current_ecg_id += len(records)
            print(f"   ✅ 输出: {out_file} (记录: {len(records)})")
        except Exception as exc:
            print(f"   ❌ 失败: {exc}")

    print(f"\n转换完成: {len(outputs)}/{len(xls_files)}")
    return outputs


def main() -> None:
    """命令行入口。"""
    parser = argparse.ArgumentParser(
        description="ECG XLS 文件解析器 - 转换为 LLM-PROMPT JSONL 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
1. 单文件转换:
   python parse_ecg_xls_to_prompt.py input.xls
2. 指定输出:
   python parse_ecg_xls_to_prompt.py input.xls -o output.jsonl
3. 设置起始 ECG ID:
   python parse_ecg_xls_to_prompt.py input.xls --ecg-id 100
4. 批量转换:
   python parse_ecg_xls_to_prompt.py -b ./ecg_data -o ./jsonl_output
        """,
    )

    parser.add_argument("input", nargs="?", help="输入 XLS 文件路径")
    parser.add_argument("-o", "--output", help="输出 JSONL 文件路径或目录")
    parser.add_argument("-b", "--batch", help="批量转换目录")
    parser.add_argument("--pattern", default="*.xls", help="批量转换文件匹配模式")
    parser.add_argument("--ecg-id", type=int, default=1, help="起始 ECG ID")
    parser.add_argument(
        "--sampling-rate",
        type=int,
        default=500,
        help="信号采样率（Hz，默认 500）",
    )

    args = parser.parse_args()

    if args.batch:
        batch_convert(
            args.batch,
            args.output,
            pattern=args.pattern,
            start_ecg_id=args.ecg_id,
            sampling_rate=args.sampling_rate,
        )
        return

    if args.input:
        try:
            convert_to_jsonl(
                args.input,
                args.output,
                start_ecg_id=args.ecg_id,
                sampling_rate=args.sampling_rate,
            )
        except Exception as exc:
            print(f"❌ 转换失败: {exc}")
            sys.exit(1)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
