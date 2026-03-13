"""策略模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class Strategy(SQLModel, table=True):
    """策略基础信息与回测摘要。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 策略名称。
    name: str
    # 策略分类，如 进攻型/防守型/长期型。
    category: str
    # 策略核心思想说明。
    thesis: str
    # 适用市场环境（可选）。
    market_regime: str | None = None
    # 回测摘要（可选）。
    backtest_summary: str | None = None
    # 创建时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)
