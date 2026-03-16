from hiveflow.domain.value_objects import PriorityLevel
from hiveflow.domain.value_objects import RiskWaterline
from hiveflow.domain.market_data import MarketBar


def classify_priority_from_risk(risk_waterline: str) -> str:
    """将风险水位映射为处理优先级。"""
    level = risk_waterline.strip().lower()
    if level in {RiskWaterline.HIGH, RiskWaterline.EXTREME}:
        return PriorityLevel.HIGH
    if level in {RiskWaterline.MEDIUM, RiskWaterline.MID}:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def calculate_max_drawdown(bars: list[MarketBar]) -> float:
    """计算最大回撤（负数或 0）。以历史最高收盘价为基准。"""
    if len(bars) < 2:
        return 0.0
    closes = [b.close for b in bars]
    peak = closes[0]
    max_dd = 0.0
    for c in closes[1:]:
        if c > peak:
            peak = c
        dd = (c - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd
