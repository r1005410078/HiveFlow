from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RebalanceSuggestion(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    delta: float
    action: str
    priority: str
    reason: str
    created_at: datetime = Field(default_factory=utc_now)
