import logging

from fastapi import FastAPI

from interfaces.http.routes_daily_run import router as daily_router
from interfaces.http.routes_factor_optimization import router as factor_optimization_router
from interfaces.http.routes_market_data import router as market_data_router
from interfaces.http.routes_portfolio import router as portfolio_router
from interfaces.http.routes_risk import router as risk_router
from interfaces.http.routes_signal import router as signal_router
from interfaces.http.routes_monitor import router as monitor_router
from interfaces.http.routes_walk_forward import router as walk_forward_router
from interfaces.adapters.market_data.symbol_name_json_middleware import SymbolNameJsonMiddleware

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="HiveFlow Quant Service",
        version="0.1.0",
        description=(
            "HiveFlow 量化核心服务 API。\n\n"
            "提供日频策略流水线（因子计算、候选排名、执行计划）"
            "与行情数据管理（同步、查询、K 线）两大模块。\n\n"
            "已纳入统一 envelope 管理的输出遵循 CLI Output Schema v1.0.0，"
            "字段含义参见 `docs/CLI_OUTPUT_SCHEMA.json`。"
        ),
        contact={"name": "HiveFlow", "email": ""},
        license_info={"name": "Private"},
    )
    app.include_router(daily_router)
    app.include_router(factor_optimization_router)
    app.include_router(market_data_router)
    app.include_router(portfolio_router)
    app.include_router(risk_router)
    app.include_router(signal_router)
    app.include_router(walk_forward_router)
    app.include_router(monitor_router)

    app.add_middleware(SymbolNameJsonMiddleware)

    @app.on_event("startup")
    def _startup() -> None:
        from interfaces.http.dependencies import create_sync_worker, has_db_config

        if has_db_config():
            worker = create_sync_worker()
            app.state.sync_worker = worker  # type: ignore[attr-defined]
            _mark_orphan_runs()
            logger.info("SyncWorker initialized")
        else:
            app.state.sync_worker = None  # type: ignore[attr-defined]
            logger.info("No DB config — SyncWorker disabled (sync falls back to inline)")

    @app.on_event("shutdown")
    def _shutdown() -> None:
        worker = getattr(app.state, "sync_worker", None)
        if worker is not None:
            logger.info("Waiting for SyncWorker to finish (max 30s)...")
            finished = worker.wait_for_completion(timeout=30)
            if not finished:
                logger.warning("SyncWorker did not finish within 30s — proceeding with shutdown")

    return app


def _mark_orphan_runs() -> None:
    from interfaces.adapters.market_data.db_connection import open_db_connection_from_env
    from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore

    try:
        conn = open_db_connection_from_env()
        store = TimescaleBarStore(conn)
        count = store.mark_orphan_runs_interrupted()
        if count:
            logger.warning("Marked %d orphan running sync_runs as interrupted", count)
        conn.close()
    except Exception:
        logger.warning("Failed to mark orphan runs on startup", exc_info=True)
