"""策略席位模型。"""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)


class StrategySlot(SQLModel, table=True):
    """策略席位定义（用途、权重、可用分类等）。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 席位名称，如 进攻席位。
    name: str
    # 席位用途说明。
    purpose: str
    # 席位允许的策略分类。
    allowed_category: str | None = None
    # 席位目标权重（0~1）。
    weight: float = 0.0
    # 是否启用该席位。
    enabled: bool = True
    # 创建时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)
