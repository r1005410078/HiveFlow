from pydantic import BaseModel, Field


class MarketDataSyncRequest(BaseModel):
    days: int = Field(ge=1)
    end_date: str
    timeframe: str
    symbols: list[str] | None = None
    universe: str | None = None
    request_id: str | None = None


class MarketDataSyncRunsQuery(BaseModel):
    days: int = Field(ge=1)
    timeframe: str | None = None
    status: str | None = None
    request_id: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class MarketDataBarsQuery(BaseModel):
    symbols: list[str] | None = None
    timeframe: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    limit: int = Field(default=5000, ge=1, le=10000)
