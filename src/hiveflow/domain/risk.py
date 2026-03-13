"""风险信号模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class RiskSignal(SQLModel, table=True):
    """标的风险水位与评分记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 标的代码。
    symbol: str
    # 风险水位标签，如 low / medium / high。
    waterline: str
    # 风险评分（数值化）。
    score: float = 0.0
    # 风险说明文本。
    note: str | None = None
    # 计算时间（UTC）。
    calculated_at: datetime = Field(default_factory=utc_now)
