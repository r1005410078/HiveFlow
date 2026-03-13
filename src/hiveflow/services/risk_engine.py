def classify_priority_from_risk(risk_waterline: str) -> str:
    """将风险水位映射为处理优先级。"""
    level = risk_waterline.strip().lower()
    if level in {"high", "extreme"}:
        return "high"
    if level in {"medium", "mid"}:
        return "medium"
    return "low"
