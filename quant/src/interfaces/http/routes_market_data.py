from fastapi import APIRouter, Depends, HTTPException, Query

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
    try:
        return service(
            days=req.days,
            end_date=req.end_date,
            timeframe=req.timeframe,
            symbols=req.symbols,
            universe=req.universe,
            request_id=req.request_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "MARKET_DATA_EMPTY", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "MARKET_DATA_PROVIDER_ERROR", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "MARKET_DATA_SYNC_FAILED", "message": str(exc)},
        ) from exc


@router.get("/sync-runs")
def get_sync_runs(
    days: int = Query(ge=1),
    timeframe: str | None = None,
    symbols: list[str] | None = Query(default=None),
    status: str | None = None,
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> dict:
    return service(days=days, timeframe=timeframe, symbols=symbols, status=status)
