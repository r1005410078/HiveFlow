from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrategySlot(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    purpose: str
    allowed_category: str | None = None
    weight: float = 0.0
    enabled: bool = True
    created_at: datetime = Field(default_factory=utc_now)
