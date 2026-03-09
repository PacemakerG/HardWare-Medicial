"""
MediGenius — core/medical_taxonomy.py
Medical department taxonomy, folder naming, and heuristic helpers.
"""

from __future__ import annotations

import re
from typing import Dict, List

GENERAL_MEDICAL_DEPARTMENT = "general_medical"

DEPARTMENT_TAXONOMY: Dict[str, Dict[str, object]] = {
    GENERAL_MEDICAL_DEPARTMENT: {
        "zh": "通用医疗",
        "aliases": ["general_medical", "general-medical", "generalmedical", "通用医疗"],
        "keywords": ["症状", "检查", "治疗", "用药", "化验", "看什么科"],
    },
    "hematology": {
        "zh": "血液科",
        "aliases": ["hematology", "blood", "血液科"],
        "keywords": ["贫血", "血红蛋白", "白细胞", "血小板", "淋巴", "骨髓", "凝血"],
    },
    "cardiology": {
        "zh": "心内科",
        "aliases": ["cardiology", "cardio", "心内科"],
        "keywords": ["胸痛", "心慌", "心悸", "心率", "心电", "胸闷", "高血压"],
    },
    "neurology": {
        "zh": "神经内科",
        "aliases": ["neurology", "neuro", "神经内科"],
        "keywords": ["头晕", "头痛", "麻木", "抽搐", "意识", "中风", "偏瘫"],
    },
    "respiratory": {
        "zh": "呼吸内科",
        "aliases": ["respiratory", "pulmonary", "呼吸内科"],
        "keywords": ["咳嗽", "咳痰", "气短", "呼吸困难", "肺", "哮喘", "发绀"],
    },
    "gastroenterology": {
        "zh": "消化内科",
        "aliases": ["gastroenterology", "gastro", "消化内科"],
        "keywords": ["腹痛", "腹泻", "恶心", "呕吐", "胃", "肠", "便血"],
    },
    "endocrinology": {
        "zh": "内分泌科",
        "aliases": ["endocrinology", "endo", "内分泌科"],
        "keywords": ["血糖", "糖尿病", "甲状腺", "激素", "多饮", "体重下降"],
    },
    "nephrology": {
        "zh": "肾内科",
        "aliases": ["nephrology", "renal", "肾内科"],
        "keywords": ["水肿", "尿蛋白", "肌酐", "肾", "尿少", "血尿"],
    },
    "rheumatology": {
        "zh": "风湿免疫科",
        "aliases": ["rheumatology", "rheum", "风湿免疫科"],
        "keywords": ["关节痛", "红斑", "免疫", "风湿", "晨僵", "狼疮"],
    },
    "infectious_disease": {
        "zh": "感染科",
        "aliases": ["infectious_disease", "infection", "感染科"],
        "keywords": ["感染", "发热", "病毒", "细菌", "传染", "乙肝"],
    },
    "general_surgery": {
        "zh": "普外科",
        "aliases": ["general_surgery", "surgery", "普外科"],
        "keywords": ["阑尾", "疝气", "外伤", "伤口", "包块", "手术"],
    },
    "orthopedics": {
        "zh": "骨科",
        "aliases": ["orthopedics", "ortho", "骨科"],
        "keywords": ["骨折", "腰痛", "关节", "膝盖", "颈椎", "扭伤"],
    },
    "gynecology": {
        "zh": "妇科",
        "aliases": ["gynecology", "gyn", "妇科"],
        "keywords": ["月经", "白带", "阴道", "盆腔", "子宫", "卵巢"],
    },
    "obstetrics": {
        "zh": "产科",
        "aliases": ["obstetrics", "ob", "产科"],
        "keywords": ["怀孕", "孕", "胎动", "产检", "宫缩", "分娩"],
    },
    "pediatrics": {
        "zh": "儿科",
        "aliases": ["pediatrics", "peds", "儿科"],
        "keywords": ["儿童", "宝宝", "小孩", "婴儿", "生长发育", "奶量"],
    },
    "dermatology": {
        "zh": "皮肤科",
        "aliases": ["dermatology", "derm", "皮肤科"],
        "keywords": ["皮疹", "瘙痒", "红斑", "湿疹", "痤疮", "脱发"],
    },
    "ent": {
        "zh": "耳鼻喉科",
        "aliases": ["ent", "otolaryngology", "耳鼻喉科"],
        "keywords": ["咽痛", "鼻塞", "耳鸣", "扁桃体", "眩晕", "流鼻血"],
    },
    "ophthalmology": {
        "zh": "眼科",
        "aliases": ["ophthalmology", "ophthal", "眼科"],
        "keywords": ["视力", "眼痛", "红眼", "飞蚊", "流泪", "畏光"],
    },
    "urology": {
        "zh": "泌尿外科",
        "aliases": ["urology", "uro", "泌尿外科"],
        "keywords": ["尿频", "尿急", "排尿", "前列腺", "肾结石", "尿痛"],
    },
    "oncology": {
        "zh": "肿瘤科",
        "aliases": ["oncology", "onco", "肿瘤科"],
        "keywords": ["肿瘤", "癌", "化疗", "放疗", "结节", "肿块"],
    },
    "emergency": {
        "zh": "急诊科",
        "aliases": ["emergency", "er", "急诊科"],
        "keywords": ["昏迷", "晕厥", "剧痛", "大出血", "休克", "急救"],
    },
}


def department_display_name(code: str) -> str:
    info = DEPARTMENT_TAXONOMY.get(code, {})
    return str(info.get("zh") or code)


def department_folder_name(code: str) -> str:
    return f"{code}_{department_display_name(code)}"


def list_department_codes() -> List[str]:
    return list(DEPARTMENT_TAXONOMY.keys())


def normalize_department_code(value: str | None) -> str | None:
    if not value:
        return None
    normalized = re.sub(r"[\s\-]+", "_", value.strip().lower())
    if normalized in DEPARTMENT_TAXONOMY:
        return normalized

    for code in DEPARTMENT_TAXONOMY:
        if normalized.startswith(f"{code}_"):
            return code

    parts = [part for part in re.split(r"[_/]", normalized) if part]
    if parts and parts[0] in DEPARTMENT_TAXONOMY:
        return parts[0]

    for code, info in DEPARTMENT_TAXONOMY.items():
        aliases = {str(alias).lower() for alias in info.get("aliases", [])}
        aliases.add(code)
        if normalized in aliases:
            return code
        if any(part in aliases for part in parts):
            return code
    return None


def infer_department_candidates(question: str, top_k: int = 3) -> List[dict]:
    q = (question or "").lower()
    scored: List[tuple[str, int]] = []
    for code, info in DEPARTMENT_TAXONOMY.items():
        if code == GENERAL_MEDICAL_DEPARTMENT:
            continue
        score = sum(1 for keyword in info.get("keywords", []) if str(keyword).lower() in q)
        if score > 0:
            scored.append((code, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    candidates = [
        {
            "name": code,
            "score": min(0.99, 0.45 + score * 0.12),
            "display_name": department_display_name(code),
        }
        for code, score in scored[:top_k]
    ]
    if not candidates:
        candidates.append(
            {
                "name": GENERAL_MEDICAL_DEPARTMENT,
                "score": 0.4,
                "display_name": department_display_name(GENERAL_MEDICAL_DEPARTMENT),
            }
        )
    return candidates


def extract_query_terms(text: str) -> List[str]:
    if not text:
        return []
    terms: List[str] = []
    seen = set()
    for token in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]{2,}", text.lower()):
        cleaned = token.strip()
        if len(cleaned) < 2 or cleaned in seen:
            continue
        seen.add(cleaned)
        terms.append(cleaned)
    return terms
