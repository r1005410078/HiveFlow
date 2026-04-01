from pydantic import BaseModel, Field


class MarketDataSyncRequest(BaseModel):
    days: int = Field(ge=1)
    end_date: str
    timeframe: str
    symbols: list[str] | None = None
    universe: str | None = None
    request_id: str | None = None

