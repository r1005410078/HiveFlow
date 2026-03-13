from hiveflow.domain.value_objects import PriorityLevel
from hiveflow.domain.value_objects import RiskWaterline


def classify_priority_from_risk(risk_waterline: str) -> str:
    """将风险水位映射为处理优先级。"""
    level = risk_waterline.strip().lower()
    if level in {RiskWaterline.HIGH, RiskWaterline.EXTREME}:
        return PriorityLevel.HIGH
    if level in {RiskWaterline.MEDIUM, RiskWaterline.MID}:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW
