"""领域值对象。"""

from enum import StrEnum


class RebalanceAction(StrEnum):
    """调仓动作。"""

    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class PriorityLevel(StrEnum):
    """处理优先级。"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class RiskWaterline(StrEnum):
    """风险水位。"""

    LOW = "low"
    MID = "mid"
    MEDIUM = "medium"
    HIGH = "high"
    EXTREME = "extreme"

