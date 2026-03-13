"""配比相关领域模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class TargetAllocation(SQLModel, table=True):
    """策略目标持仓记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 生成该目标持仓的策略名称。
    strategy_name: str
    # 标的代码，如 BTC、AAPL。
    symbol: str
    # 目标权重（0~1）。
    target_weight: float
    # 生成时间（UTC）。
    generated_at: datetime = Field(default_factory=utc_now)


class AssetMix(SQLModel, table=True):
    """账户级资产配比（进攻/防守/长期）。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 进攻仓位权重（0~1）。
    attack_weight: float = 0.0
    # 防守仓位权重（0~1）。
    defense_weight: float = 0.0
    # 长期仓位权重（0~1）。
    long_term_weight: float = 0.0
    # 最近更新时间（UTC）。
    updated_at: datetime = Field(default_factory=utc_now)
