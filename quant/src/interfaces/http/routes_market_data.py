from fastapi import APIRouter, Depends, Query

from interfaces.http.dependencies import (
    MarketDataQueryService,
    MarketDataSyncService,
    get_market_data_query_service,
    get_market_data_sync_service,
)
from interfaces.http.schemas_market_data import MarketDataSyncRequest

router = APIRouter(prefix="/v1/market-data", tags=["market-data"])


@router.post("/sync")
def post_sync(
    req: MarketDataSyncRequest,
    service: MarketDataSyncService = Depends(get_market_data_sync_service),
) -> dict:
    return service(
        days=req.days,
        end_date=req.end_date,
        timeframe=req.timeframe,
        symbols=req.symbols,
        universe=req.universe,
        request_id=req.request_id,
    )


@router.get("/sync-runs")
def get_sync_runs(
    days: int = Query(ge=1),
    timeframe: str | None = None,
    symbols: list[str] | None = Query(default=None),
    status: str | None = None,
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> dict:
    return service(days=days, timeframe=timeframe, symbols=symbols, status=status)

