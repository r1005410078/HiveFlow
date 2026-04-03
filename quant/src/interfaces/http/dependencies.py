from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException

from application.daily_run_service import run_daily
from application.factor_optimization import run_factor_optimization
from application.pipeline_compare_service import run_pipeline_compare
from application.market_data.bars_query_service import BarsQueryService
from application.market_data.query_service import QueryService
from application.market_data.sync_service import SyncService
from interfaces.adapters.market_data.akshare_quote_adapter import AkshareQuoteAdapter
from interfaces.adapters.market_data.akshare_universe_adapter import AkshareUniverseAdapter
from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
from interfaces.adapters.market_data.tencent_quote_adapter import TencentQuoteAdapter
from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore


DailyRunService = Callable[[str], dict]
PipelineCompareService = Callable[[str, str, int], dict]
FactorOptimizationService = Callable[[str, str, list[str], dict[str, float]], dict]
MarketDataSyncService = Callable[..., dict]
MarketDataUniverseSyncService = Callable[..., dict]
MarketDataQueryService = Callable[..., dict]
MarketDataBarsQueryService = Callable[..., dict]


def get_daily_run_service() -> DailyRunService:
    # Provider only: wire application service into FastAPI dependency graph.
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of: run_daily(as_of=as_of, root=None, bar_store=bar_store)


def get_pipeline_compare_service() -> PipelineCompareService:
    # Provider only: wire application service into FastAPI dependency graph.
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda start_date, end_date, top_n: run_pipeline_compare(
        start_date=start_date,
        end_date=end_date,
        top_n=top_n,
        root=None,
        bar_store=bar_store,
    )


def get_factor_optimization_service() -> FactorOptimizationService:
    # Provider only: wire application service into FastAPI dependency graph.
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda start_date, end_date, factor_names, constraints: run_factor_optimization(
        start_date=start_date,
        end_date=end_date,
        factor_names=factor_names,
        constraints=constraints,
        bar_store=bar_store,
    )


class _NoopQuoteRepo:
    def fetch(self, symbols, as_of, timeframe):
        return []


class _FallbackQuoteRepo:
    def __init__(self, primary, secondary):
        self._primary = primary
        self._secondary = secondary

    def fetch(self, symbols, as_of, timeframe):
        primary_error = None
        try:
            rows = self._primary.fetch(symbols=symbols, as_of=as_of, timeframe=timeframe)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001 - source-specific failures should degrade.
            primary_error = exc

        try:
            rows = self._secondary.fetch(symbols=symbols, as_of=as_of, timeframe=timeframe)
            if rows:
                return rows
        except Exception as secondary_exc:  # noqa: BLE001 - source-specific failures should degrade.
            if primary_error is not None:
                raise RuntimeError(
                    f"both market data sources failed: primary={primary_error}; secondary={secondary_exc}"
                ) from secondary_exc
            # Primary returned empty: this can be a valid non-trading slice.
            # If secondary also fails here, degrade to empty rows and let upper
            # layers decide whether the full sync window is acceptable.
            return []

        if primary_error is not None:
            raise RuntimeError(
                f"primary market data source failed and secondary returned empty: {primary_error}"
            ) from primary_error

        return []


class _InMemoryBarStore:
    def upsert_bars(self, rows):
        return len(rows)

    def get_sync_run_by_request_id(self, request_id):
        del request_id
        return None

    def get_checkpoints(self, symbols, timeframe):
        del symbols, timeframe
        return {}

    def upsert_checkpoints(self, checkpoints):
        del checkpoints
        return None

    def insert_sync_run(self, payload):
        del payload
        return None

    def list_sync_runs(self, days, timeframe=None, status=None, request_id=None, limit=None):
        del days, timeframe, status, request_id, limit
        return [
            {
                "run_id": "run_demo_001",
                "request_id": "req_demo_001",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "selection_mode": "default",
                "symbols_hash": "demo_symbols_hash",
                "effective_symbols_count": 1,
                "written_rows": 1,
                "manifest_ids": ["mf_demo_001"],
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
            }
        ]

    def list_bars(self, symbols=None, timeframe=None, start_date=None, end_date=None, limit=None):
        del start_date, end_date, limit
        symbol = (symbols or ["600519.SH"])[0]
        return [
            {
                "symbol": symbol,
                "timeframe": timeframe or "1d",
                "bar_time": "2026-04-01T15:00:00+08:00",
                "open": 1450.0,
                "high": 1468.0,
                "low": 1442.0,
                "close": 1459.44,
                "volume": 29125.0,
                "amount": 4256185472.0,
                "adj_factor": 1.0,
                "data_source": "demo",
            }
        ]


def _build_bar_store():
    if has_db_config():
        try:
            return TimescaleBarStore(open_db_connection_from_env())
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "MARKET_DATA_DB_UNAVAILABLE",
                    "message": "database is unavailable for market-data sync",
                    "reason": str(exc),
                },
            ) from exc
    return _InMemoryBarStore()


def _build_read_bar_store():
    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MARKET_DATA_DB_UNAVAILABLE",
                "message": "database is required for market-data read endpoints",
            },
        )
    try:
        return TimescaleBarStore(open_db_connection_from_env())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "MARKET_DATA_DB_UNAVAILABLE",
                "message": "database is unavailable for market-data read endpoints",
                "reason": str(exc),
            },
        ) from exc


def _build_quote_repo():
    if has_db_config():
        try:
            primary = TencentQuoteAdapter()
        except Exception:
            try:
                return AkshareQuoteAdapter()
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail={
                        "code": "MARKET_DATA_SOURCE_UNAVAILABLE",
                        "message": "tencent/akshare market data sources are unavailable",
                        "reason": str(exc),
                    },
                ) from exc
        try:
            secondary = AkshareQuoteAdapter()
        except Exception:
            return primary
        return _FallbackQuoteRepo(primary=primary, secondary=secondary)
    return _NoopQuoteRepo()


def get_market_data_sync_service() -> MarketDataSyncService:
    service = SyncService(quote_repo=_build_quote_repo(), bar_store=_build_bar_store())
    return service.sync


def get_market_data_universe_sync_service() -> MarketDataUniverseSyncService:
    try:
        universe_source = AkshareUniverseAdapter()
    except Exception:
        universe_source = None
    service = SyncService(
        quote_repo=_build_quote_repo(),
        bar_store=_build_bar_store(),
        universe_source_repo=universe_source,
    )
    return service.sync_universe_symbols


def get_market_data_query_service() -> MarketDataQueryService:
    service = QueryService(bar_store=_build_read_bar_store())
    return service.query


def get_market_data_bars_query_service() -> MarketDataBarsQueryService:
    service = BarsQueryService(bar_store=_build_read_bar_store())
    return service.query
