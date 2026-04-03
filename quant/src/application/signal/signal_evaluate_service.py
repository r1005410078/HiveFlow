from __future__ import annotations

import logging
import math
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pandas as pd

from application.contracts.cli_output import ok_output
from application.factor.basic_factor_service import compute_basic_factor_snapshot_from_bars
from application.signal.signal_engineering_service import compute_signal_matrix

_EVAL_VERSION = "l3-eval-v1.0"
_BENCHMARK_SYMBOL = "000300.SH"
_DEFAULT_SYMBOLS = [
    "000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ",
]
_MIN_SPEARMAN_PAIRS = 3
_DRIFT_THRESHOLD = 2.0
_TURNOVER_STABLE_THRESHOLD = 0.5
_MIN_DAYS_FOR_DRIFT = 5
_FACTOR_BAR_LOOKBACK_DAYS = 180

_logger = logging.getLogger(__name__)


def _compute_daily_ic(signal_matrix: dict, forward_returns: dict[str, float]) -> dict:
    result: dict[str, float] = {}
    fwd_series = pd.Series(forward_returns)

    for factor in signal_matrix.get("factor_names", []):
        signal_series = pd.Series({
            r["symbol"]: r["signal_value"]
            for r in signal_matrix["rows"]
            if r["factor_name"] == factor and not math.isnan(r["signal_value"])
        })
        common = signal_series.index.intersection(fwd_series.index)
        if len(common) >= _MIN_SPEARMAN_PAIRS:
            ic = signal_series[common].corr(fwd_series[common], method="spearman")
            result[factor] = round(float(ic), 6) if not math.isnan(ic) else float("nan")
        else:
            result[factor] = float("nan")

    composite_series = pd.Series({
        cs["symbol"]: cs["composite_score"]
        for cs in signal_matrix.get("composite_scores", [])
        if not math.isnan(cs["composite_score"])
    })
    common = composite_series.index.intersection(fwd_series.index)
    if len(common) >= _MIN_SPEARMAN_PAIRS:
        ic = composite_series[common].corr(fwd_series[common], method="spearman")
        result["composite"] = round(float(ic), 6) if not math.isnan(ic) else float("nan")
    else:
        result["composite"] = float("nan")

    return result


def _aggregate_ic_series(daily_ics: list[float]) -> dict:
    valid = [v for v in daily_ics if not math.isnan(v)]
    if not valid:
        return {"mean_ic": float("nan"), "ic_std": float("nan"), "ic_ir": float("nan"), "hit_rate": float("nan")}
    mean_ic = statistics.mean(valid)
    ic_std = statistics.pstdev(valid) if len(valid) > 1 else 0.0
    ic_ir = round(mean_ic / ic_std, 6) if ic_std > 0 else 0.0
    hit_rate = sum(1 for v in valid if v > 0) / len(valid)
    return {
        "mean_ic": round(mean_ic, 6),
        "ic_std": round(ic_std, 6),
        "ic_ir": ic_ir,
        "hit_rate": round(hit_rate, 6),
    }


def _compute_factor_drift(
    factor_name: str,
    baseline_means: list[float],
    recent_means: list[float],
) -> dict:
    bl_valid = [v for v in baseline_means if not math.isnan(v)]
    rc_valid = [v for v in recent_means if not math.isnan(v)]

    if not bl_valid or not rc_valid:
        return {
            "factor_name": factor_name,
            "baseline_mean": 0.0, "baseline_std": 0.0,
            "recent_mean": 0.0, "drift_z": 0.0, "drift_flag": False,
        }

    bl_mean = statistics.mean(bl_valid)
    bl_std = statistics.pstdev(bl_valid) if len(bl_valid) > 1 else 0.0
    rc_mean = statistics.mean(rc_valid)

    if bl_std == 0.0:
        drift_z = 0.0
    else:
        drift_z = (rc_mean - bl_mean) / bl_std

    return {
        "factor_name": factor_name,
        "baseline_mean": round(bl_mean, 6),
        "baseline_std": round(bl_std, 6),
        "recent_mean": round(rc_mean, 6),
        "drift_z": round(drift_z, 4),
        "drift_flag": abs(drift_z) > _DRIFT_THRESHOLD,
    }


def _kendall_tau_distance(ranking_a: list[str], ranking_b: list[str]) -> float:
    n = len(ranking_a)
    if n < 2:
        return 0.0
    index_b = {s: i for i, s in enumerate(ranking_b)}
    discordant = 0
    pairs = n * (n - 1) // 2
    for i in range(n):
        for j in range(i + 1, n):
            a_i, a_j = ranking_a[i], ranking_a[j]
            if index_b.get(a_i, 0) > index_b.get(a_j, 0):
                discordant += 1
    return discordant / pairs


def _get_forward_returns(
    bar_store, symbols: list[str], as_of: str, forward_days: int,
) -> dict[str, float]:
    end = (date.fromisoformat(as_of) + timedelta(days=forward_days + 5)).isoformat()
    bars = bar_store.list_bars(
        symbols=symbols, timeframe="1d",
        start_date=as_of, end_date=end, limit=len(symbols) * (forward_days + 10),
    )

    by_symbol: dict[str, list[dict]] = {}
    for b in bars:
        by_symbol.setdefault(b["symbol"], []).append(b)

    result: dict[str, float] = {}
    for sym, sym_bars in by_symbol.items():
        sorted_bars = sorted(sym_bars, key=lambda b: b["bar_time"])
        base_bars = [b for b in sorted_bars if b["bar_time"][:10] <= as_of]
        fwd_bars = [b for b in sorted_bars if b["bar_time"][:10] > as_of]
        if not base_bars or len(fwd_bars) < forward_days:
            continue
        base_close = base_bars[-1]["close"]
        fwd_close = fwd_bars[forward_days - 1]["close"]
        if base_close == 0:
            continue
        result[sym] = round((fwd_close / base_close) - 1.0, 6)

    return result


def _compute_signal_for_date(bar_store, symbols: list[str], as_of: str) -> dict | None:
    try:
        start = (date.fromisoformat(as_of) - timedelta(days=_FACTOR_BAR_LOOKBACK_DAYS)).isoformat()
        bar_rows = bar_store.list_bars(
            symbols=symbols, timeframe="1d",
            start_date=start, end_date=as_of, limit=len(symbols) * 200,
        )
        if not bar_rows or len(bar_rows) < len(symbols) * 61:
            return None
        try:
            benchmark_start = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()
            benchmark_rows = bar_store.list_bars(
                symbols=[_BENCHMARK_SYMBOL], timeframe="1d",
                start_date=benchmark_start, end_date=as_of, limit=60,
            )
        except Exception:
            benchmark_rows = None
        factor_snapshot = compute_basic_factor_snapshot_from_bars(
            as_of=as_of, symbols=symbols,
            bar_rows=bar_rows, benchmark_rows=benchmark_rows,
        )
        return compute_signal_matrix(factor_snapshot)
    except Exception:
        _logger.warning("signal evaluate: failed for %s", as_of, exc_info=True)
        return None


def _get_composite_ranking(signal_matrix: dict) -> list[str]:
    scores = signal_matrix.get("composite_scores", [])
    valid = [(cs["symbol"], cs["composite_score"]) for cs in scores if not math.isnan(cs["composite_score"])]
    valid.sort(key=lambda x: x[1], reverse=True)
    return [s for s, _ in valid]


def run_signal_evaluation(
    start_date: str,
    end_date: str,
    forward_days: int,
    bar_store,
) -> dict:
    if bar_store is None:
        return {
            "schema_version": "1.0.0",
            "command": "hf signal evaluate",
            "run_id": f"run_eval_{str(uuid4())[:8]}",
            "status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {},
            "warnings": [],
            "errors": [{"code": "BAR_STORE_REQUIRED", "message": "Signal evaluation requires database with real bar data"}],
        }

    symbols = list(_DEFAULT_SYMBOLS)
    d_start = date.fromisoformat(start_date)
    d_end = date.fromisoformat(end_date)

    if d_start >= d_end:
        return {
            "schema_version": "1.0.0",
            "command": "hf signal evaluate",
            "run_id": f"run_eval_{str(uuid4())[:8]}",
            "status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {},
            "warnings": [],
            "errors": [{"code": "INVALID_DATE_RANGE", "message": f"start_date ({start_date}) must be before end_date ({end_date})"}],
        }

    current = d_start
    daily_results: list[dict] = []
    warnings: list[dict] = []

    while current <= d_end - timedelta(days=forward_days):
        as_of = current.isoformat()
        signal_matrix = _compute_signal_for_date(bar_store, symbols, as_of)
        if signal_matrix is None:
            warnings.append({
                "code": "SKIPPED_DATE_INSUFFICIENT_BARS",
                "message": f"Skipped {as_of}: insufficient bar data for factor computation",
            })
            current += timedelta(days=1)
            continue

        fwd_returns = _get_forward_returns(bar_store, symbols, as_of, forward_days)
        if not fwd_returns:
            warnings.append({
                "code": "SKIPPED_DATE_NO_FORWARD_RETURNS",
                "message": f"Skipped {as_of}: no forward returns available",
            })
            current += timedelta(days=1)
            continue

        ic_result = _compute_daily_ic(signal_matrix, fwd_returns)
        pre_stats = {
            ts["factor_name"]: ts["pre_winsorize"]["mean"]
            for ts in signal_matrix.get("transform_stats", [])
        }
        ranking = _get_composite_ranking(signal_matrix)

        daily_results.append({
            "date": as_of,
            "ic": ic_result,
            "pre_winsorize_means": pre_stats,
            "coverage_rate": signal_matrix.get("coverage_rate", 0.0),
            "ranking": ranking,
        })

        current += timedelta(days=1)

    if not daily_results:
        return ok_output(
            command="hf signal evaluate",
            run_id=f"run_eval_{str(uuid4())[:8]}",
            data={
                "eval_version": _EVAL_VERSION,
                "start_date": start_date, "end_date": end_date,
                "forward_days": forward_days,
                "trading_days_evaluated": 0,
                "symbols": symbols,
                "ic_report": None, "drift_diagnostics": None,
            },
            warnings=warnings + [{"code": "NO_VALID_EVALUATION_DAYS", "message": "No dates had sufficient data for evaluation"}],
        )

    factor_names = list(daily_results[0]["ic"].keys())
    factor_names = [f for f in factor_names if f != "composite"]

    per_factor_ic: list[dict] = []
    for fn in factor_names:
        daily_ics = [d["ic"].get(fn, float("nan")) for d in daily_results]
        agg = _aggregate_ic_series(daily_ics)
        per_factor_ic.append({
            "factor_name": fn,
            **agg,
            "daily_ic": [
                {"date": d["date"], "ic": d["ic"].get(fn, float("nan"))}
                for d in daily_results
            ],
        })

    composite_daily_ics = [d["ic"].get("composite", float("nan")) for d in daily_results]
    composite_agg = _aggregate_ic_series(composite_daily_ics)
    composite_report = {
        **composite_agg,
        "daily_ic": [
            {"date": d["date"], "ic": d["ic"].get("composite", float("nan"))}
            for d in daily_results
        ],
    }

    ic_report = {"per_factor": per_factor_ic, "composite": composite_report}

    drift_diagnostics = None
    n_days = len(daily_results)
    if n_days >= _MIN_DAYS_FOR_DRIFT:
        drift_window = max(3, n_days // 4)
        baseline_days = n_days - drift_window

        factor_drift: list[dict] = []
        for fn in factor_names:
            bl_means = [d["pre_winsorize_means"].get(fn, float("nan")) for d in daily_results[:baseline_days]]
            rc_means = [d["pre_winsorize_means"].get(fn, float("nan")) for d in daily_results[baseline_days:]]
            factor_drift.append(_compute_factor_drift(fn, bl_means, rc_means))

        bl_cov = [d["coverage_rate"] for d in daily_results[:baseline_days]]
        rc_cov = [d["coverage_rate"] for d in daily_results[baseline_days:]]
        bl_cov_valid = [v for v in bl_cov if not math.isnan(v)]
        rc_cov_valid = [v for v in rc_cov if not math.isnan(v)]
        bl_cov_mean = statistics.mean(bl_cov_valid) if bl_cov_valid else 0.0
        bl_cov_std = statistics.pstdev(bl_cov_valid) if len(bl_cov_valid) > 1 else 0.0
        rc_cov_mean = statistics.mean(rc_cov_valid) if rc_cov_valid else 0.0
        cov_drift_z = ((rc_cov_mean - bl_cov_mean) / bl_cov_std) if bl_cov_std > 0 else 0.0

        turnovers: list[float] = []
        for i in range(1, n_days):
            prev_rank = daily_results[i - 1]["ranking"]
            curr_rank = daily_results[i]["ranking"]
            if prev_rank and curr_rank and set(prev_rank) == set(curr_rank):
                turnovers.append(_kendall_tau_distance(prev_rank, curr_rank))

        mean_turnover = round(statistics.mean(turnovers), 4) if turnovers else 0.0
        max_turnover = round(max(turnovers), 4) if turnovers else 0.0

        drift_diagnostics = {
            "drift_window": drift_window,
            "baseline_days": baseline_days,
            "factor_drift": factor_drift,
            "coverage_drift": {
                "baseline_mean": round(bl_cov_mean, 4),
                "recent_mean": round(rc_cov_mean, 4),
                "drift_z": round(cov_drift_z, 4),
                "drift_flag": abs(cov_drift_z) > _DRIFT_THRESHOLD,
            },
            "rank_turnover": {
                "mean_turnover": mean_turnover,
                "max_turnover": max_turnover,
                "stable": mean_turnover < _TURNOVER_STABLE_THRESHOLD,
            },
        }
    else:
        warnings.append({
            "code": "INSUFFICIENT_DAYS_FOR_DRIFT",
            "message": f"Need at least {_MIN_DAYS_FOR_DRIFT} evaluation days for drift detection, got {n_days}",
        })

    data = {
        "eval_version": _EVAL_VERSION,
        "start_date": start_date,
        "end_date": end_date,
        "forward_days": forward_days,
        "trading_days_evaluated": n_days,
        "symbols": symbols,
        "ic_report": ic_report,
        "drift_diagnostics": drift_diagnostics,
    }

    return ok_output(
        command="hf signal evaluate",
        run_id=f"run_eval_{start_date.replace('-', '')}_{end_date.replace('-', '')}_{str(uuid4())[:8]}",
        data=data,
        warnings=warnings if warnings else None,
    )
