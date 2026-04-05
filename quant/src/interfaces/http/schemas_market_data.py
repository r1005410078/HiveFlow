from pydantic import BaseModel, Field


class MarketDataSyncRequest(BaseModel):
    days: int = Field(ge=1)
    end_date: str
    timeframe: str
    symbols: list[str] | None = None
    universe: str | None = None
    request_id: str | None = None


class MarketDataUniverseSyncRequest(BaseModel):
    universe: str = Field(description="目标标的池名称，如 csi300 / zz500 / all_a / self_select / follow")
    provider: str = Field(default="akshare", description="第三方来源，当前仅支持 akshare")


class MarketDataSymbolNamesSyncRequest(BaseModel):
    universes: list[str] | None = Field(
        default=None,
        description="要拉取中文简称的标的池；省略则 csi300 + zz500 + all_a",
    )
    provider: str = Field(default="akshare", description="第三方来源，当前仅支持 akshare")


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


class MarketDataBarsBundleRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, description="至少一个标的代码")
    timeframes: list[str] = Field(min_length=1, description="至少一个输出周期")
    start_date: str | None = None
    end_date: str | None = None
    limit_per_timeframe: int = Field(default=5000, ge=1, le=10000)
