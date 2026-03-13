from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DecisionLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    summary: str
    decision_type: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class UserPreference(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    key: str
    value: str
    updated_at: datetime = Field(default_factory=utc_now)
