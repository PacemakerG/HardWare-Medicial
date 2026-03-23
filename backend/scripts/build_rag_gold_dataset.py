"""
Curate a manually reviewed gold RAG evaluation dataset from the seed dataset.

The seed dataset is document-generated and noisy. This script selects a smaller
high-quality subset and rewrites questions / anchors / keywords into a more
human-usable benchmark set.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CURATION = {
    "dermatology_001": {
        "question": "淋菌性咽炎常用哪些治疗方案？",
        "expected_anchor_text": "淋菌性咽炎头孢曲松250mg一次肌肉注射",
        "expected_keywords": ["淋菌性咽炎", "头孢曲松", "环丙沙星", "左氧氟沙星"],
    },
    "dermatology_004": {
        "question": "二期梅毒一般在什么时候发生？有哪些典型皮肤黏膜表现？",
        "expected_anchor_text": "二期梅毒常发生于硬下疳消退3〜4周后",
        "expected_keywords": ["二期梅毒", "硬下疳消退", "梅毒疹", "皮肤黏膜损害"],
    },
    "dermatology_006": {
        "question": "二期梅毒常见的斑疹性梅毒疹和黏膜损害有哪些特点？",
        "expected_anchor_text": "斑疹性梅毒疹和黏膜损害多见于二期梅毒",
        "expected_keywords": ["斑疹性梅毒疹", "黏膜损害", "二期梅毒", "传染性强"],
    },
    "ent_001": {
        "question": "慢性外耳道炎常用哪些滴耳药物？怎么使用？",
        "expected_anchor_text": "急慢性外耳道炎和真菌感染可用滴耳液",
        "expected_keywords": ["慢性外耳道炎", "滴耳", "防腐", "止痒"],
    },
    "ent_002": {
        "question": "变应性鼻炎应用莫米松鼻喷雾剂有什么作用和用法？",
        "expected_anchor_text": "莫米松喷雾剂具有抗炎与抗过敏作用",
        "expected_keywords": ["变应性炎", "莫米松", "抗炎", "抗过敏"],
    },
    "infectious_disease_002": {
        "question": "甲型流感为什么容易引起大流行？它有哪些流行特点？",
        "expected_anchor_text": "甲型流感流行特点是突然发生迅速传播",
        "expected_keywords": ["甲型流感", "突然发生", "迅速传播", "抗原性转变"],
    },
    "infectious_disease_005": {
        "question": "某些传染病进入多尿期后可能出现哪些并发症？需要注意哪些电解质问题？",
        "expected_anchor_text": "多尿期若补充不足或继发感染可发生休克和低钠低钾",
        "expected_keywords": ["多尿期", "继发感染", "继发性休克", "低血钠", "低血钾"],
    },
    "neurology_001": {
        "question": "TIA患者在什么情况下建议住院治疗？ABCD2评分怎么用？",
        "expected_anchor_text": "TIA短期卒中风险评估常用ABCD2评分",
        "expected_keywords": ["TIA", "ABCD2评分", "建议住院治疗", "72小时内"],
    },
    "neurology_002": {
        "question": "额叶癫痫发作持续时间和发作形式有哪些典型特点？",
        "expected_anchor_text": "发作持续时间短形式刻板常在夜间入睡中发作",
        "expected_keywords": ["发作持续时间短", "部分性发作", "继发全面性发作", "夜间发作"],
    },
    "ophthalmology_001": {
        "question": "ETDRS视力检查法有什么特点，临床上怎么使用？",
        "expected_anchor_text": "ETDRS采用对数视力表进行视力检查",
        "expected_keywords": ["ETDRS", "对数视力表", "视力检查", "临床试验"],
    },
    "ophthalmology_004": {
        "question": "角膜炎的病理变化通常分哪几个阶段？浸润期有什么表现？",
        "expected_anchor_text": "角膜炎病理过程分浸润期溃疡期消退期和愈合期",
        "expected_keywords": ["角膜炎", "浸润期", "溃疡期", "视力下降", "刺激症状"],
    },
    "ophthalmology_006": {
        "question": "色觉检查常用哪些方法？假同色图检查有什么优缺点？",
        "expected_anchor_text": "目前临床多用主观检查假同色图应用最广",
        "expected_keywords": ["色觉检测", "主观检查", "假同色图", "简便", "不能精确判定"],
    },
    "pediatrics_005": {
        "question": "病原明确后，肺炎链球菌肺炎如何选择抗生素？",
        "expected_anchor_text": "肺炎链球菌对青霉素敏感时可改用青霉素",
        "expected_keywords": ["肺炎链球菌", "青霉素耐药", "药物敏感试验", "青霉素"],
    },
    "pediatrics_006": {
        "question": "青春期是怎样一个发育阶段？有哪些主要生理变化？",
        "expected_anchor_text": "青春期是儿童到成人的过渡阶段",
        "expected_keywords": ["青春期", "过渡阶段", "生长发育突增", "第二性征", "性成熟"],
    },
    "general_medical_001": {
        "question": "短波治疗有哪些禁忌？为什么急性感染炎症只能用小剂量超短波治疗？",
        "expected_anchor_text": "短波不能用于急性感染炎症只能用小剂量超短波治疗",
        "expected_keywords": ["短波治疗", "急性感染炎症", "小剂量超短波", "热灼伤"],
    },
    "general_medical_004": {
        "question": "HbA1c能否作为糖尿病诊断标准？我国目前为什么不推荐单独采用？",
        "expected_anchor_text": "我国目前尚不推荐采用HbA1c诊断糖尿病",
        "expected_keywords": ["HbA1c", "糖尿病", "诊断标准", "我国尚不推荐"],
    },
    "general_medical_005": {
        "question": "特发性肺纤维化患者为什么要预防流感和肺炎？它的自然病程和预后怎样？",
        "expected_anchor_text": "IPF诊断后中位生存期为2至3年",
        "expected_keywords": ["预防流感和肺炎", "IPF", "中位生存期", "自然病程", "预后"],
    },
    "general_surgery_003": {
        "question": "纠正缺水后为什么要预防低钾血症？低渗性缺水有哪些处理要点？",
        "expected_anchor_text": "纠正缺水后排钾量增加应注意预防低钾血症",
        "expected_keywords": ["排钾量增加", "低钾血症", "低渗性缺水", "纠正缺水"],
    },
    "general_surgery_006": {
        "question": "骨样骨瘤有哪些典型临床表现？CT检查和治疗要点是什么？",
        "expected_anchor_text": "CT检查有助于发现瘤巢",
        "expected_keywords": ["瘤巢", "CT检查", "夜间痛", "阿司匹林止痛", "手术治疗"],
    },
}


def build_gold_dataset(seed_path: Path, output_path: Path) -> int:
    seed_rows = {
        row["id"]: row
        for row in (
            json.loads(line)
            for line in seed_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    curated_rows = []
    for sample_id, override in CURATION.items():
        base = dict(seed_rows[sample_id])
        base.update(override)
        base["dataset_source"] = "manual_gold_v1"
        curated_rows.append(base)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in curated_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(curated_rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build manually curated RAG gold dataset.")
    parser.add_argument(
        "--seed",
        type=str,
        default="backend/data/eval/rag_eval_dataset_v1.jsonl",
        help="Seed dataset path.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="backend/data/eval/rag_eval_dataset_gold_v1.jsonl",
        help="Output gold dataset path.",
    )
    args = parser.parse_args()

    count = build_gold_dataset(Path(args.seed), Path(args.output))
    print(json.dumps({"output": args.output, "samples": count}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
