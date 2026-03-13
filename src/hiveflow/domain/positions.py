"""实际持仓模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class Position(SQLModel, table=True):
    """账户中的单个标的持仓记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 标的代码，如 BTC、600519、AAPL。
    symbol: str
    # 持仓数量。
    quantity: float = 0.0
    # 当前市值（按账户计价货币）。
    market_value: float = 0.0
    # 持仓权重（0~1）。
    weight: float = 0.0
    # 最近更新时间（UTC）。
    updated_at: datetime = Field(default_factory=utc_now)
