from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

from application.daily_run_service import run_daily
from application.execution.execution_service import run_execution_plan
from application.factor_optimization import run_factor_optimization
from application.market_data.sync_worker import SyncWorker
from application.pipeline_compare_service import run_pipeline_compare
from application.portfolio.portfolio_optimize_service import run_portfolio_optimize
from application.pretrade.pretrade_service import run_pretrade_check
from application.risk.risk_gate_service import run_risk_check
from application.signal.signal_evaluate_service import run_signal_evaluation
from application.signal.signal_engineering_service import run_signal_snapshot
from application.contracts.cli_output import ok_output
from application.system.doctor_service import run_system_doctor
from application.walk_forward_service import run_walk_forward
from application.market_data.bars_query_service import BarsQueryService
from application.market_data.coverage_service import get_coverage
from application.market_data.instruments_list_service import InstrumentsListService
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
MarketDataSymbolNamesSyncService = Callable[..., dict]
MarketDataQueryService = Callable[..., dict]
MarketDataBarsQueryService = Callable[..., dict]
MarketDataBarsBundleQueryService = Callable[..., dict]
MarketDataInstrumentsListService = Callable[..., dict]
MarketDataCoverageQuery = Callable[..., dict]
SignalSnapshotService = Callable[[str], dict]
SignalEvaluateService = Callable[[str, str, int], dict]
PortfolioOptimizeService = Callable[..., dict]
RiskCheckService = Callable[..., dict]
PretradeService = Callable[..., dict]
WalkForwardService = Callable[..., dict]
HealthReportService = Callable[[str], dict]
ExecutionPlanService = Callable[..., dict]
ExperimentConfigSnapshotFn = Callable[[str], dict]
ExperimentConfigListFn = Callable[[str | None, int], dict]
ExperimentConfigGetFn = Callable[[str], dict]
SystemDoctorEnvelopeFn = Callable[[int], dict]


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


def get_signal_snapshot_service() -> SignalSnapshotService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of: run_signal_snapshot(as_of=as_of, bar_store=bar_store)


def get_signal_evaluate_service() -> SignalEvaluateService:
    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BAR_STORE_REQUIRED",
                "message": "Signal evaluation requires database with real bar data",
            },
        )
    try:
        bar_store = TimescaleBarStore(open_db_connection_from_env())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "BAR_STORE_REQUIRED",
                "message": f"Signal evaluation requires database: {exc}",
            },
        ) from exc
    return lambda start, end, fwd: run_signal_evaluation(
        start_date=start, end_date=end, forward_days=fwd, bar_store=bar_store,
    )


def get_portfolio_optimize_service() -> PortfolioOptimizeService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, alpha, prev_weights, lambda_risk, lambda_tc, w_max, ind_max, lookback_days: run_portfolio_optimize(
        as_of=as_of,
        alpha=alpha,
        prev_weights=prev_weights,
        lambda_risk=lambda_risk,
        lambda_tc=lambda_tc,
        w_max=w_max,
        ind_max=ind_max,
        lookback_days=lookback_days,
        bar_store=bar_store,
    )


def get_risk_check_service() -> RiskCheckService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, target_weights, prev_weights: run_risk_check(
        as_of=as_of,
        target_weights=target_weights,
        prev_weights=prev_weights,
        bar_store=bar_store,
    )


def get_pretrade_service() -> PretradeService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, target_weights, notional: run_pretrade_check(
        as_of=as_of,
        target_weights=target_weights,
        bar_store=bar_store,
        notional=notional,
    )


def get_execution_service() -> ExecutionPlanService:
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of, target_weights, pretrade, notional: run_execution_plan(
        as_of=as_of,
        target_weights=target_weights,
        pretrade=pretrade,
        bar_store=bar_store,
        notional=notional,
    )


def get_walk_forward_service() -> WalkForwardService:
    # Provider only: wire application service into FastAPI dependency graph.
    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda start_date, end_date, warm_up_days=180, test_window_days=63, step_days=21, cost_bp=0.0: run_walk_forward(
        start_date=start_date,
        end_date=end_date,
        warm_up_days=warm_up_days,
        test_window_days=test_window_days,
        step_days=step_days,
        cost_bp=cost_bp,
        bar_store=bar_store,
    )


def get_health_report_service() -> HealthReportService:
    from application.monitor.health_report_service import run_health_report

    bar_store = None
    if has_db_config():
        try:
            bar_store = TimescaleBarStore(open_db_connection_from_env())
        except Exception:
            bar_store = None
    return lambda as_of: run_health_report(as_of, bar_store=bar_store)


def _experiment_config_store_or_none() -> TimescaleBarStore | None:
    if not has_db_config():
        return None
    try:
        return TimescaleBarStore(open_db_connection_from_env())
    except Exception:
        return None


def get_experiment_config_snapshot_fn() -> ExperimentConfigSnapshotFn:
    from application.experiment.experiment_config_service import snapshot_current

    store = _experiment_config_store_or_none()
    return lambda note: snapshot_current(note, store=store)


def get_experiment_config_list_fn() -> ExperimentConfigListFn:
    from application.experiment.experiment_config_service import list_experiment_configs

    store = _experiment_config_store_or_none()
    return lambda layer, limit: list_experiment_configs(store=store, layer=layer, limit=limit)


def get_experiment_config_get_fn() -> ExperimentConfigGetFn:
    from application.experiment.experiment_config_service import get_experiment_config

    store = _experiment_config_store_or_none()
    return lambda config_id: get_experiment_config(config_id, store=store)


def get_market_data_coverage_query() -> MarketDataCoverageQuery:
    """Provider only: wire `get_coverage` into the HTTP dependency graph."""
    return get_coverage


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

    def update_sync_run(self, run_id, payload):
        del run_id, payload
        return None

    def list_sync_runs(self, days, timeframe=None, status=None, request_id=None, run_id=None, limit=None):
        del days, timeframe, status, request_id, run_id, limit
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

    def list_storage_bars(
        self,
        symbols=None,
        storage_timeframe="1m",
        start_date=None,
        end_date=None,
        limit=None,
        order="asc",
    ):
        del start_date, end_date, limit, order
        symbol = (symbols or ["600519.SH"])[0]
        return [
            {
                "symbol": symbol,
                "timeframe": storage_timeframe,
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

    def list_symbols_with_min_bars_in_window(
        self,
        *,
        storage_timeframe: str,
        start_date: str,
        end_date: str,
        min_bars: int,
        after_symbol: str | None,
        limit: int,
    ):
        del storage_timeframe, start_date, end_date, min_bars, after_symbol, limit
        return (["600519.SH"], False)


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


def get_market_data_symbol_names_sync_service() -> MarketDataSymbolNamesSyncService:
    try:
        universe_source = AkshareUniverseAdapter()
    except Exception:
        universe_source = None
    service = SyncService(
        quote_repo=_build_quote_repo(),
        bar_store=_build_bar_store(),
        universe_source_repo=universe_source,
    )
    return service.merge_symbol_names_only


def get_market_data_query_service() -> MarketDataQueryService:
    service = QueryService(bar_store=_build_read_bar_store())
    return service.query


def get_market_data_bars_query_service() -> MarketDataBarsQueryService:
    service = BarsQueryService(bar_store=_build_read_bar_store())
    return service.query


def get_market_data_bars_bundle_query_service() -> MarketDataBarsBundleQueryService:
    service = BarsQueryService(bar_store=_build_read_bar_store())
    return service.query_bundle


def _try_read_bar_store_optional() -> TimescaleBarStore | None:
    if not has_db_config():
        return None
    try:
        return TimescaleBarStore(open_db_connection_from_env())
    except Exception:
        return None


def get_market_data_instruments_list_service() -> MarketDataInstrumentsListService:
    store = _try_read_bar_store_optional()
    return InstrumentsListService(bar_store=store).list_instruments


def get_system_doctor_envelope() -> SystemDoctorEnvelopeFn:
    """Provider: `GET /v1/system/doctor` → full CLI envelope (`data` = quant aggregate)."""
    from uuid import uuid4

    store = _try_read_bar_store_optional()

    def _envelope(sync_days: int) -> dict:
        payload = run_system_doctor(bar_store=store, sync_days=sync_days)
        return ok_output("hf doctor", str(uuid4()), payload)

    return _envelope


# ── async sync worker factories ───────────────────────────────

def _bar_store_factory():
    return TimescaleBarStore(open_db_connection_from_env())


def _quote_repo_factory():
    return _build_quote_repo()


def _universe_source_factory():
    try:
        return AkshareUniverseAdapter()
    except Exception:
        return None


def create_sync_worker() -> SyncWorker:
    return SyncWorker(
        bar_store_factory=_bar_store_factory,
        quote_repo_factory=_quote_repo_factory,
        universe_source_factory=_universe_source_factory,
    )


def get_sync_worker(request: Request) -> SyncWorker | None:
    return getattr(request.app.state, "sync_worker", None)
