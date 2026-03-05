"""
MediGenius — agents/planner.py
PlannerAgent: decides whether to use RAG retriever or direct LLM.
"""

from app.core.state import AgentState

# ── Medical Keywords ───────────────────────────────────────────────────────────
MEDICAL_KEYWORDS = [
    # Symptoms (English & Chinese)
    "fever", "发烧", "pain", "疼痛", "headache", "头痛", "nausea", "恶心", "vomiting", "呕吐", "diarrhea", "腹泻", "cough", "健康",
    "acne", "痤疮", "pimple", "青春痘", "skin", "皮肤", "rash", "皮疹", "itch", "痒", "cold", "感冒", "flu", "流感",
    "shortness of breath", "呼吸急促", "chest pain", "胸痛", "abdominal pain", "腹痛", "back pain", "背痛",
    "joint pain", "关节痛", "muscle pain", "肌肉痛", "fatigue", "疲劳", "weakness", "虚弱", "dizziness", "头晕",
    "confusion", "困惑", "memory loss", "记忆丧失", "seizure", "numbness", "麻木", "tingling", "刺痛", "swelling", "肿胀",
    "bleeding", "出血", "bruising", "瘀伤", "weight loss", "体重减轻", "weight gain", "体重增加",
    "appetite loss", "食欲不振", "sleep problems", "睡眠问题", "insomnia", "失眠",
    # Conditions (English & Chinese)
    "cancer", "癌症", "diabetes", "糖尿病", "hypertension", "高血压", "heart disease", "心脏病", "stroke", "中风", "asthma", "哮喘",
    "copd", "慢阻肺", "pneumonia", "肺炎", "bronchitis", "支气管炎", "covid", "coronavirus", "新冠", "冠状病毒",
    "infection", "感染", "virus", "病毒", "bacteria", "细菌", "fungal", "真菌", "arthritis", "关节炎", "osteoporosis", "骨质疏松",
    "thyroid", "甲状腺", "kidney disease", "肾脏疾病", "liver disease", "肝病", "hepatitis", "肝炎", "depression", "抑郁",
    "anxiety", "焦虑", "bipolar", "躁郁症", "schizophrenia", "精神分裂症", "alzheimer", "老年痴呆", "parkinson", "帕金森", "epilepsy", "癫痫",
    # Medical terms (English & Chinese)
    "treatment", "治疗", "therapy", "疗法", "medication", "medicine", "药物", "医学", "prescription", "处方", "dosage", "剂量",
    "side effects", "副作用", "diagnosis", "诊断", "prognosis", "预后", "surgery", "手术", "operation", "操作",
    "procedure", "程序", "test", "测试", "lab results", "实验室结果", "blood test", "验血", "x-ray", "X射线", "mri", "核磁共振",
    "ct scan", "CT扫描", "ultrasound", "超声", "biopsy", "活检", "screening", "筛查", "prevention", "预防", "vaccine", "疫苗",
    "immunization", "免疫", "rehabilitation", "康复", "recovery", "恢复", "chronic", "慢性", "acute", "急性",
    "syndrome", "综合征", "disorder", "障碍", "symptom", "症状", "cure", "治愈", "remedy", "补救", "doctor", "医生", "hospital", "医院",
    # Body parts (English & Chinese)
    "heart", "心脏", "lung", "肺", "kidney", "肾", "liver", "肝", "brain", "大脑", "stomach", "胃", "intestine", "肠",
    "blood", "血液", "bone", "骨骼", "muscle", "肌肉", "nerve", "神经", "eye", "眼睛", "ear", "耳朵", "throat", "喉咙",
    "neck", "脖子", "spine", "脊柱", "joint", "关节", "head", "头部", "chest", "胸部", "abdomen", "腹部", "leg", "腿", "arm", "手臂",
    # Support Keywords
    "manual", "手册", "advice", "建议", "handle", "处理"
]


def PlannerAgent(state: AgentState) -> AgentState:
    """Decide whether to use RAG retriever or direct LLM based on question content."""
    question = state["question"].lower()
    contains_medical = any(kw in question for kw in MEDICAL_KEYWORDS)
    state["current_tool"] = "retriever" if contains_medical else "llm_agent"
    state["retry_count"] = 0
    return state
