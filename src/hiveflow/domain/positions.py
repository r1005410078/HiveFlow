from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Position(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    quantity: float = 0.0
    market_value: float = 0.0
    weight: float = 0.0
    updated_at: datetime = Field(default_factory=utc_now)
