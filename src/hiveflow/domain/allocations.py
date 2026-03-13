from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TargetAllocation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str
    symbol: str
    target_weight: float
    generated_at: datetime = Field(default_factory=utc_now)


class AssetMix(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    attack_weight: float = 0.0
    defense_weight: float = 0.0
    long_term_weight: float = 0.0
    updated_at: datetime = Field(default_factory=utc_now)
