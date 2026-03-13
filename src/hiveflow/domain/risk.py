from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RiskSignal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    waterline: str
    score: float = 0.0
    note: str | None = None
    calculated_at: datetime = Field(default_factory=utc_now)
