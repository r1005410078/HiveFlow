from __future__ import annotations

from collections.abc import Callable

from application.daily_run_service import run_daily
from application.market_data.query_service import QueryService
from application.market_data.sync_service import SyncService
from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore


DailyRunService = Callable[[str], dict]
MarketDataSyncService = Callable[..., dict]
MarketDataQueryService = Callable[..., dict]


def get_daily_run_service() -> DailyRunService:
    # Provider only: wire application service into FastAPI dependency graph.
    return lambda as_of: run_daily(as_of=as_of, root=None)


class _NoopQuoteRepo:
    def fetch(self, symbols, as_of, timeframe):
        return []


class _InMemoryBarStore:
    def upsert_bars(self, rows):
        return len(rows)

    def list_sync_runs(self, days, timeframe=None, symbols=None, status=None):
        del status
        return [
            {
                "run_id": "run_demo_001",
                "date": "2026-04-01",
                "status": "success",
                "timeframe": timeframe or "1d",
                "symbols_count": len(symbols or []),
                "manifest_id": "mf_demo_001",
                "days": days,
            }
        ]


def _build_bar_store():
    if has_db_config():
        return TimescaleBarStore(open_db_connection_from_env())
    return _InMemoryBarStore()


def get_market_data_sync_service() -> MarketDataSyncService:
    service = SyncService(quote_repo=_NoopQuoteRepo(), bar_store=_build_bar_store())
    return service.sync


def get_market_data_query_service() -> MarketDataQueryService:
    service = QueryService(bar_store=_build_bar_store())
    return service.query
