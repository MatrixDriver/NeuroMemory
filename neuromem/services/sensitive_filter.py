"""Sensitive content filter for trait creation."""

# Categories that should never be inferred as traits
SENSITIVE_TRAIT_CATEGORIES = frozenset({
    "mental_health",       # 心理健康、精神状态
    "medical",             # 医疗历史、诊断
    "political",           # 政治倾向
    "religious",           # 宗教信仰
    "sexual_orientation",  # 性取向、性别认同
    "financial_details",   # 收入、债务、资产
    "criminal_history",    # 犯罪记录
    "addiction",           # 成瘾行为
    "abuse_trauma",        # 虐待、创伤
})

_SENSITIVE_KEYWORDS = {
    # 心理健康
    "抑郁", "焦虑", "双相", "精神分裂", "自杀", "ptsd", "心理疾病", "恐惧症",
    "depression", "anxiety", "bipolar", "schizophrenia", "suicide",
    # 医疗
    "诊断", "处方药", "病症", "癌症", "hiv",
    "diagnosis", "prescription", "disease",
    # 政治宗教
    "政党", "共和党", "民主党", "信仰", "基督", "佛教", "伊斯兰", "无神论",
    "republican", "democrat", "religion", "christian", "muslim", "atheist",
    # 财务
    "年收入", "年薪", "工资", "债务", "贷款", "负债",
    "salary", "income", "debt",
    # 成瘾与创伤
    "吸毒", "酗酒", "赌博成瘾", "虐待", "性侵", "家暴",
    "drug abuse", "alcoholism", "gambling", "assault",
}


def is_sensitive_trait(content: str) -> bool:
    """Check if trait content touches a sensitive category."""
    lower = content.lower()
    return any(kw in lower for kw in _SENSITIVE_KEYWORDS)
