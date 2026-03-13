from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Strategy(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str
    category: str
    thesis: str
    market_regime: str | None = None
    backtest_summary: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
