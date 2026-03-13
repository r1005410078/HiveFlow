"""调仓建议模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class RebalanceSuggestion(SQLModel, table=True):
    """实际与目标偏差计算后的调仓建议记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 标的代码。
    symbol: str
    # 偏差值（实际权重 - 目标权重）。
    delta: float
    # 建议动作，如 buy / sell / hold。
    action: str
    # 处理优先级，如 high / medium / low。
    priority: str
    # 建议原因说明。
    reason: str
    # 建议生成时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)
