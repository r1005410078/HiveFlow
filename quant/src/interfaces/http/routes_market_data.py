from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from interfaces.http.dependencies import (
    MarketDataBarsQueryService,
    MarketDataQueryService,
    MarketDataSyncService,
    MarketDataSymbolNamesSyncService,
    MarketDataUniverseSyncService,
    get_market_data_bars_query_service,
    get_market_data_query_service,
    get_market_data_sync_service,
    get_market_data_symbol_names_sync_service,
    get_market_data_universe_sync_service,
    get_sync_worker,
)
from interfaces.http.schemas_market_data import (
    MarketDataSyncRequest,
    MarketDataSymbolNamesSyncRequest,
    MarketDataUniverseSyncRequest,
)

router = APIRouter(prefix="/v1/market-data", tags=["market-data"])


def _get_bar_store_for_read():
    from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
    from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore

    if has_db_config():
        return TimescaleBarStore(open_db_connection_from_env())

    class _Stub:
        def get_sync_run_by_request_id(self, *a, **kw):
            return None
        def get_sync_run_by_id(self, *a, **kw):
            return None
        def get_running_sync_run(self, *a, **kw):
            return None
        def insert_sync_run_running(self, *a, **kw):
            pass
        def request_sync_cancel(self, *a, **kw):
            return False
        def list_failed_symbols_for_retry(self, *a, **kw):
            return []

    return _Stub()


@router.post(
    "/sync",
    summary="触发行情数据同步",
    description=(
        "从数据源拉取指定标的、时间范围、时间频率的 K 线数据并写入数据库。\n\n"
        "异步模式：返回 202 + run_id，后台 Worker 执行同步；"
        "通过 GET /v1/market-data/sync-runs/{run_id} 轮询进度。\n\n"
        "无 DB 模式：直接同步执行并返回 200。"
    ),
    response_model=None,
    responses={
        202: {"description": "异步任务已提交"},
        200: {"description": "幂等命中或同步模式直接完成"},
        409: {"description": "已有同步任务运行中"},
        422: {"description": "参数错误或数据源返回为空"},
        503: {"description": "数据源连接失败"},
    },
)
def post_sync(
    req: MarketDataSyncRequest,
    request: Request,
    service: MarketDataSyncService = Depends(get_market_data_sync_service),
):
    worker = get_sync_worker(request)

    if worker is None:
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
            raise HTTPException(status_code=422, detail={"code": "MARKET_DATA_EMPTY", "message": str(exc)}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={"code": "MARKET_DATA_PROVIDER_ERROR", "message": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"code": "MARKET_DATA_SYNC_FAILED", "message": str(exc)}) from exc

    bar_store = _get_bar_store_for_read()

    if req.request_id:
        existing = bar_store.get_sync_run_by_request_id(req.request_id)
        if existing:
            if existing.get("status") == "success":
                return existing
            if existing.get("status") == "running":
                return JSONResponse(
                    status_code=202,
                    content={"run_id": existing["run_id"], "status": "running", "message": "sync already in progress"},
                )

    if worker.is_running():
        running_id = worker.current_run_id()
        raise HTTPException(
            status_code=409,
            detail={"code": "SYNC_ALREADY_RUNNING", "running_run_id": running_id},
        )

    from hashlib import sha256 as _sha256

    run_id = str(uuid4())
    symbols_list = req.symbols or []
    symbols_hash = _sha256(",".join(sorted(symbols_list)).encode()).hexdigest() if symbols_list else ""

    bar_store.insert_sync_run_running({
        "run_id": run_id,
        "request_id": req.request_id,
        "phase": "pending",
        "days": req.days,
        "end_date": req.end_date,
        "timeframe": req.timeframe,
        "selection_mode": "symbols" if req.symbols else ("universe" if req.universe else "default"),
        "symbols_hash": symbols_hash,
        "effective_symbols_count": len(symbols_list),
        "manifest_ids": [],
    })

    submitted = worker.submit_sync(run_id, {
        "days": req.days,
        "end_date": req.end_date,
        "timeframe": req.timeframe,
        "symbols": req.symbols,
        "universe": req.universe,
        "request_id": req.request_id,
    })

    if not submitted:
        raise HTTPException(
            status_code=409,
            detail={"code": "SYNC_ALREADY_RUNNING", "running_run_id": worker.current_run_id()},
        )

    return JSONResponse(
        status_code=202,
        content={"run_id": run_id, "status": "running", "message": "sync job submitted"},
    )


@router.get(
    "/sync-runs/{run_id}",
    summary="查询单个同步任务详情（含进度）",
    responses={200: {"description": "任务详情"}, 404: {"description": "任务不存在"}},
)
def get_sync_run_detail(run_id: str) -> dict:
    bar_store = _get_bar_store_for_read()
    run = bar_store.get_sync_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "SYNC_RUN_NOT_FOUND"})
    return run


@router.post(
    "/sync-runs/{run_id}/cancel",
    summary="请求取消运行中的同步任务",
    responses={200: {"description": "取消请求已接受或任务已结束（幂等）"}, 404: {"description": "任务不存在"}},
)
def post_sync_run_cancel(run_id: str) -> dict:
    bar_store = _get_bar_store_for_read()
    run = bar_store.get_sync_run_by_id(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "SYNC_RUN_NOT_FOUND"})

    if run["status"] != "running":
        return {"run_id": run_id, "cancel_accepted": False, "message": "already finished", "status": run["status"]}

    accepted = bar_store.request_sync_cancel(run_id)
    return {"run_id": run_id, "cancel_accepted": accepted, "status": "cancelling" if accepted else run["status"]}


@router.post(
    "/sync-runs/{run_id}/retry-failed",
    summary="仅对上次任务的失败标的发起新同步",
    responses={
        202: {"description": "新任务已提交"},
        404: {"description": "源任务不存在"},
        409: {"description": "已有同步任务运行中"},
        422: {"description": "源任务仍在运行或无可重试标的"},
    },
)
def post_sync_run_retry_failed(
    run_id: str,
    request: Request,
) -> JSONResponse:
    bar_store = _get_bar_store_for_read()
    source_run = bar_store.get_sync_run_by_id(run_id)
    if source_run is None:
        raise HTTPException(status_code=404, detail={"code": "SYNC_RUN_NOT_FOUND"})

    if source_run["status"] == "running":
        raise HTTPException(status_code=422, detail={"code": "SOURCE_RUN_STILL_RUNNING"})

    failed_symbols = bar_store.list_failed_symbols_for_retry(run_id)
    if not failed_symbols:
        raise HTTPException(status_code=422, detail={"code": "NO_FAILED_SYMBOLS", "message": "no terminal-failed symbols to retry"})

    worker = get_sync_worker(request)
    if worker is None:
        raise HTTPException(status_code=501, detail={"code": "ASYNC_SYNC_NOT_AVAILABLE"})

    if worker.is_running():
        raise HTTPException(status_code=409, detail={"code": "SYNC_ALREADY_RUNNING", "running_run_id": worker.current_run_id()})

    new_run_id = str(uuid4())
    retry_symbols = [f["symbol"] for f in failed_symbols]

    bar_store.insert_sync_run_running({
        "run_id": new_run_id,
        "request_id": None,
        "phase": "pending",
        "days": source_run["days"],
        "end_date": source_run["end_date"],
        "timeframe": source_run["timeframe"],
        "selection_mode": "retry_failed",
        "symbols_hash": "",
        "effective_symbols_count": len(retry_symbols),
        "manifest_ids": [],
    })

    submitted = worker.submit_sync(new_run_id, {
        "days": source_run["days"],
        "end_date": source_run["end_date"],
        "timeframe": source_run["timeframe"],
        "symbols": retry_symbols,
    })

    if not submitted:
        raise HTTPException(status_code=409, detail={"code": "SYNC_ALREADY_RUNNING"})

    return JSONResponse(
        status_code=202,
        content={"run_id": new_run_id, "status": "running", "message": "retry-failed sync job submitted", "source_run_id": run_id},
    )


@router.post(
    "/universes/sync",
    summary="从第三方接口同步标的池定义",
    description=(
        "将第三方接口返回的标的列表同步到本地 universe 文件。\n\n"
        "异步模式：返回 202 + run_id。"
    ),
    response_model=None,
)
def post_universe_sync(
    req: MarketDataUniverseSyncRequest,
    request: Request,
    service: MarketDataUniverseSyncService = Depends(get_market_data_universe_sync_service),
):
    worker = get_sync_worker(request)

    if worker is None:
        try:
            return service(universe=req.universe, provider=req.provider)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail={"code": "UNIVERSE_SYNC_INVALID_ARGUMENT", "message": str(exc)}) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail={"code": "UNIVERSE_SYNC_PROVIDER_ERROR", "message": str(exc)}) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail={"code": "UNIVERSE_SYNC_FAILED", "message": str(exc)}) from exc

    if worker.is_running():
        raise HTTPException(status_code=409, detail={"code": "SYNC_ALREADY_RUNNING", "running_run_id": worker.current_run_id()})

    bar_store = _get_bar_store_for_read()
    run_id = str(uuid4())

    bar_store.insert_sync_run_running({
        "run_id": run_id,
        "request_id": None,
        "phase": "pending",
        "days": 0,
        "end_date": "1970-01-01",
        "timeframe": "universe",
        "selection_mode": "universe_sync",
        "symbols_hash": "",
        "effective_symbols_count": 0,
        "manifest_ids": [],
    })

    submitted = worker.submit_universe_sync(run_id, {
        "universe": req.universe,
        "provider": req.provider,
    })

    if not submitted:
        raise HTTPException(status_code=409, detail={"code": "SYNC_ALREADY_RUNNING"})

    return JSONResponse(
        status_code=202,
        content={"run_id": run_id, "status": "running", "message": "universe sync job submitted"},
    )


@router.post(
    "/universes/symbol-names/sync",
    summary="仅合并 symbol_names.json",
    description=(
        "从 akshare 拉取指定标的池（或默认 csi300+zz500+all_a）的代码与中文简称，"
        "合并写入 quant/config/universes/symbol_names.json；不修改各 universe .txt。"
        "若部分池失败，仍返回 200，JSON 中 status=partial 且含 failed_universes；"
        "仅当全部失败时返回错误。"
    ),
    response_model=None,
)
def post_universe_symbol_names_sync(
    req: MarketDataSymbolNamesSyncRequest,
    service: MarketDataSymbolNamesSyncService = Depends(get_market_data_symbol_names_sync_service),
):
    try:
        return service(universes=req.universes, provider=req.provider)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "SYMBOL_NAMES_SYNC_INVALID_ARGUMENT", "message": str(exc)},
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "SYMBOL_NAMES_SYNC_PROVIDER_ERROR", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "SYMBOL_NAMES_SYNC_FAILED", "message": str(exc)},
        ) from exc


@router.get(
    "/sync-runs",
    summary="查询同步任务历史",
    description="查询过去 N 天内的数据同步任务记录。",
)
def get_sync_runs(
    days: int = Query(ge=1),
    timeframe: str | None = Query(default=None),
    status: str | None = Query(default=None),
    request_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
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
    description="查询指定标的、时间范围的 K 线数据。",
)
def get_bars(
    symbols: list[str] | None = Query(default=None),
    timeframe: str | None = Query(default=None),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=10000),
    service: MarketDataBarsQueryService = Depends(get_market_data_bars_query_service),
) -> dict:
    return service(
        symbols=symbols,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
