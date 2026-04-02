from fastapi import APIRouter, Depends, HTTPException, Query

from interfaces.http.dependencies import (
    MarketDataBarsQueryService,
    MarketDataQueryService,
    MarketDataSyncService,
    get_market_data_bars_query_service,
    get_market_data_query_service,
    get_market_data_sync_service,
)
from interfaces.http.schemas_market_data import MarketDataSyncRequest

router = APIRouter(prefix="/v1/market-data", tags=["market-data"])


@router.post(
    "/sync",
    summary="触发行情数据同步",
    description=(
        "从数据源拉取指定标的、时间范围、时间频率的 K 线数据并写入数据库。\n\n"
        "- `days`：向前回溯天数，从 `end_date` 起算\n"
        "- `timeframe`：时间频率，如 `1d`（日线）、`1h`（小时线）\n"
        "- `symbols`：标的列表，留空则使用 `universe` 全量同步\n"
        "- `universe`：预设标的池名称（与 `symbols` 二选一）\n"
        "- `request_id`：幂等键，相同 `request_id` 重复调用不会重复写入"
    ),
    response_description="同步结果摘要，含写入条数与耗时",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "request_id": "sync_20260401_1d",
                        "status": "ok",
                        "bars_written": 120,
                        "symbols_synced": ["600519.SH", "000001.SZ"],
                        "timeframe": "1d",
                    }
                }
            }
        },
        422: {"description": "参数错误或数据源返回为空"},
        503: {"description": "数据源连接失败"},
    },
)
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


@router.get(
    "/sync-runs",
    summary="查询同步任务历史",
    description=(
        "查询过去 N 天内的数据同步任务记录，支持按时间频率、状态、`request_id` 过滤。\n\n"
        "常用于排查同步失败或确认最近一次同步是否成功。"
    ),
    response_description="同步任务列表，按创建时间降序排列",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "runs": [
                            {
                                "request_id": "sync_20260401_1d",
                                "status": "completed",
                                "timeframe": "1d",
                                "bars_written": 120,
                                "created_at": "2026-04-01T08:00:00+08:00",
                            }
                        ],
                        "total": 1,
                    }
                }
            }
        }
    },
)
def get_sync_runs(
    days: int = Query(ge=1, description="向前查询天数，最小为 1"),
    timeframe: str | None = Query(default=None, description="时间频率过滤，如 `1d`"),
    status: str | None = Query(default=None, description="任务状态过滤：`completed` / `failed` / `running`"),
    request_id: str | None = Query(default=None, description="按幂等键精确查询"),
    limit: int = Query(default=100, ge=1, le=1000, description="最多返回条数，默认 100"),
    service: MarketDataQueryService = Depends(get_market_data_query_service),
) -> dict:
    return service(
        days=days,
        timeframe=timeframe,
        status=status,
        request_id=request_id,
        limit=limit,
    )


@router.get(
    "/bars",
    summary="查询 K 线数据",
    description=(
        "查询指定标的、时间范围的 K 线数据。\n\n"
        "- `symbols`：标的列表，如 `600519.SH,000001.SZ`；留空返回全量\n"
        "- `timeframe`：时间频率，如 `1d`（日线）\n"
        "- `start_date` / `end_date`：查询区间（含两端），格式 `YYYY-MM-DD`\n"
        "- `limit`：最多返回条数，默认 5000，上限 10000\n\n"
        "数据已按 `(symbol, timestamp)` 升序排列。"
    ),
    response_description="K 线数据列表",
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "bars": [
                            {
                                "symbol": "600519.SH",
                                "timestamp": "2026-04-01T00:00:00+08:00",
                                "open": 1680.0,
                                "high": 1710.5,
                                "low": 1675.0,
                                "close": 1702.3,
                                "volume": 12345678,
                                "timeframe": "1d",
                            }
                        ],
                        "total": 1,
                    }
                }
            }
        }
    },
)
def get_bars(
    symbols: list[str] | None = Query(default=None, description="标的代码列表，如 `600519.SH`"),
    timeframe: str | None = Query(default=None, description="时间频率，如 `1d`"),
    start_date: str | None = Query(default=None, description="开始日期，格式 `YYYY-MM-DD`"),
    end_date: str | None = Query(default=None, description="结束日期，格式 `YYYY-MM-DD`"),
    limit: int = Query(default=5000, ge=1, le=10000, description="最多返回条数，默认 5000"),
    service: MarketDataBarsQueryService = Depends(get_market_data_bars_query_service),
) -> dict:
    return service(
        symbols=symbols,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
