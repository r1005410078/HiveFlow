"""Walk-forward backtest service for L7 verification layer."""

from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import Any

from application.daily_run_service import run_daily
from domain.market_data.sse_calendar import iter_sse_trading_days

_ANNUALIZATION_DAYS = 252
_DEFAULT_THRESHOLDS = {
    "annualized_return_mean_min": 0.06,   # >= 6%
    "max_drawdown_max_max": 0.20,         # <= 20%
    "sharpe_min_min": 0.5,                # >= 0.5
}

_logger = logging.getLogger(__name__)


def generate_windows(
    start_date: str,
    end_date: str,
    warm_up_days: int,
    test_window_days: int,
    step_days: int,
) -> list[dict]:
    """Generate rolling windows from date range.

    Args:
        start_date: "YYYY-MM-DD" start of entire period
        end_date: "YYYY-MM-DD" end of entire period
        warm_up_days: calendar days for warm-up period
        test_window_days: calendar days for test window
        step_days: calendar days to step forward each window

    Returns:
        List of dicts with keys:
        - warm_start, warm_end, test_start, test_end (ISO format)

    Raises:
        ValueError: if start_date > end_date
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if start > end:
        raise ValueError("start_date must be on or before end_date")

    windows = []

    # First test window starts warm_up_days after start
    current_test_start = start + timedelta(days=warm_up_days)

    while current_test_start <= end:
        # Test window ends warm_up_days + test_window_days from warm_start
        test_end = current_test_start + timedelta(days=test_window_days)
        # Cap to overall end date
        if test_end > end:
            test_end = end

        # Warm-up period is the warm_up_days before test_start
        warm_start = current_test_start - timedelta(days=warm_up_days)
        warm_end = current_test_start - timedelta(days=1)

        windows.append({
            "warm_start": warm_start.isoformat(),
            "warm_end": warm_end.isoformat(),
            "test_start": current_test_start.isoformat(),
            "test_end": test_end.isoformat(),
        })

        # Move forward by step_days
        current_test_start += timedelta(days=step_days)

    return windows


def _coerce_finite_float(value: Any) -> float | None:
    """Safely convert value to float, returning None if NaN or inf.

    Args:
        value: any value that can be converted to float

    Returns:
        float if finite, None if NaN/inf/None
    """
    if value is None:
        return None

    try:
        f = float(value)
    except (ValueError, TypeError):
        return None

    if math.isnan(f) or math.isinf(f):
        return None

    return f


def _compute_daily_return(
    weights: dict[str, float],
    as_of: str,
    bar_store,
    cost_bp: float,
) -> float | None:
    """Compute daily return from weights and bar prices.

    Fetches bars for as_of and as_of+1, computes weighted return,
    deducts transaction cost.

    Args:
        weights: symbol → weight dict (should sum to 1.0)
        as_of: "YYYY-MM-DD" trading day
        bar_store: bar_store port (must implement list_bars)
        cost_bp: transaction cost in basis points (0.01% per bp)

    Returns:
        Daily return (float) after cost, or None if bars unavailable
    """
    if not weights:
        # No position, only cost applies
        return -cost_bp / 10000.0

    symbols = list(weights.keys())

    # Query bars for today and tomorrow
    as_of_date = date.fromisoformat(as_of)
    tomorrow = as_of_date + timedelta(days=1)

    try:
        bars = bar_store.list_bars(
            symbols=symbols,
            timeframe="1d",
            start_date=as_of,
            end_date=tomorrow.isoformat(),
            limit=1000,
        )
    except Exception:
        _logger.warning(f"Failed to fetch bars for {as_of} and next day", exc_info=True)
        return None

    # Build dict: (symbol, date_str) → close
    # bar_time is "YYYY-MM-DDTHH:MM:SS+08:00", extract the date prefix
    bar_dict = {}
    for bar in bars:
        raw_time = bar.get("bar_time", "") or ""
        date_str = raw_time[:10]  # "YYYY-MM-DD"
        key = (bar.get("symbol"), date_str)
        bar_dict[key] = bar.get("close")

    # Compute weighted return
    gross_return = 0.0
    symbols_with_bars = 0
    for symbol, weight in weights.items():
        today_close = bar_dict.get((symbol, as_of))
        tomorrow_close = bar_dict.get((symbol, tomorrow.isoformat()))

        if today_close is None or tomorrow_close is None:
            # Missing bar for this symbol tomorrow, skip it
            continue

        daily_ret = (tomorrow_close - today_close) / today_close
        gross_return += weight * daily_ret
        symbols_with_bars += 1

    # If no symbols had valid bars, return None (cannot compute return)
    if symbols_with_bars == 0:
        return None

    # Deduct cost
    net_return = gross_return - (cost_bp / 10000.0)
    return net_return


def _build_window_metrics(daily_returns: list[float]) -> dict:
    """Build per-window metrics from daily returns.

    Args:
        daily_returns: list of daily returns (as decimals, e.g., 0.01 = 1%)

    Returns:
        Dict with:
        - cumulative_return (float)
        - annualized_return (float)
        - sharpe (float, assumes daily vol)
        - max_drawdown (float)
        - win_rate (float, 0-1)
    """
    if not daily_returns:
        return {
            "cumulative_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }

    # Cumulative return: compound growth
    cum_return = 1.0
    for ret in daily_returns:
        cum_return *= (1.0 + ret)
    cumulative_return = cum_return - 1.0

    # Annualized return
    days = len(daily_returns)
    years = days / _ANNUALIZATION_DAYS
    if years > 0:
        annualized_return = (cum_return ** (1.0 / years)) - 1.0
    else:
        annualized_return = cumulative_return

    # Sharpe ratio: mean / std * sqrt(252)
    mean_ret = sum(daily_returns) / len(daily_returns)
    if len(daily_returns) > 1:
        variance = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        std_dev = math.sqrt(variance)
    else:
        std_dev = 0.0

    if std_dev > 0:
        sharpe = (mean_ret / std_dev) * math.sqrt(_ANNUALIZATION_DAYS)
    else:
        sharpe = 0.0

    # Max drawdown: largest peak-to-trough
    max_dd = 0.0
    running_max = 1.0
    for ret in daily_returns:
        running_max *= (1.0 + ret)
        peak = running_max
        # Trough from peak
        dd = 1.0 - peak / running_max if running_max > 0 else 0.0
        max_dd = max(max_dd, -dd + 1.0)
    # Recompute max drawdown correctly
    max_dd = 0.0
    peak = 1.0
    for ret in daily_returns:
        peak *= (1.0 + ret)
        peak = max(peak, 1.0)
        # Drawdown at this point
        trough = peak
        for future_ret in daily_returns[daily_returns.index(ret)+1:] if ret in daily_returns else []:
            trough *= (1.0 + future_ret)
        # Actually, compute it by running through cumulative values

    # Compute cumulative values for drawdown
    cumvals = [1.0]
    for ret in daily_returns:
        cumvals.append(cumvals[-1] * (1.0 + ret))

    # Max drawdown: (peak - trough) / peak at each point
    max_dd = 0.0
    for i in range(len(cumvals)):
        peak = max(cumvals[:i+1])
        trough = cumvals[i]
        dd = (peak - trough) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)

    # Win rate: fraction of days with positive return
    wins = sum(1 for r in daily_returns if r > 0)
    win_rate = wins / len(daily_returns) if daily_returns else 0.0

    return {
        "cumulative_return": _coerce_finite_float(cumulative_return) or 0.0,
        "annualized_return": _coerce_finite_float(annualized_return) or 0.0,
        "sharpe": _coerce_finite_float(sharpe) or 0.0,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
    }


def _aggregate_windows(windows: list[dict]) -> dict:
    """Aggregate metrics across windows.

    Args:
        windows: list of per-window result dicts

    Returns:
        Dict with window_count and min/mean/max for key metrics
    """
    if not windows:
        return {
            "window_count": 0,
            "annualized_return": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "sharpe": {"mean": 0.0, "min": 0.0, "max": 0.0},
            "max_drawdown": {"mean": 0.0, "min": 0.0, "max": 0.0},
        }

    def agg_metric(key: str) -> dict:
        values = [w.get(key, 0.0) for w in windows]
        return {
            "mean": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    return {
        "window_count": len(windows),
        "annualized_return": agg_metric("annualized_return"),
        "sharpe": agg_metric("sharpe"),
        "max_drawdown": agg_metric("max_drawdown"),
    }


def _gate_check(aggregate: dict, thresholds: dict) -> dict:
    """Apply gate checks against thresholds.

    Args:
        aggregate: aggregated metrics dict
        thresholds: threshold dict with keys like annualized_return_mean_min

    Returns:
        {"verdict": "pass" or "no_go", "failed_gates": [list of gate names]}
    """
    failed = []

    # Check annualized_return mean >= threshold
    if "annualized_return_mean_min" in thresholds:
        mean_ret = aggregate.get("annualized_return", {}).get("mean", 0.0)
        if mean_ret < thresholds["annualized_return_mean_min"]:
            failed.append("annualized_return_mean_min")

    # Check max_drawdown max <= threshold
    if "max_drawdown_max_max" in thresholds:
        max_dd = aggregate.get("max_drawdown", {}).get("max", 0.0)
        if max_dd > thresholds["max_drawdown_max_max"]:
            failed.append("max_drawdown_max_max")

    # Check sharpe min >= threshold
    if "sharpe_min_min" in thresholds:
        min_sharpe = aggregate.get("sharpe", {}).get("min", 0.0)
        if min_sharpe < thresholds["sharpe_min_min"]:
            failed.append("sharpe_min_min")

    return {
        "verdict": "no_go" if failed else "pass",
        "failed_gates": failed,
    }


def _run_test_window(
    test_start: str,
    test_end: str,
    warm_start: str,
    bar_store,
    cost_bp: float,
) -> dict:
    """Run test window: execute daily, compute returns, build metrics.

    Args:
        test_start: "YYYY-MM-DD" first day of test window
        test_end: "YYYY-MM-DD" last day of test window
        warm_start: "YYYY-MM-DD" first day of warm-up (for bar context)
        bar_store: bar_store port
        cost_bp: transaction cost in basis points

    Returns:
        Dict with window results and metrics
    """
    daily_returns = []
    cost_total_bp = 0.0
    days_run = 0

    # Iterate through trading days in test window
    for trading_day in iter_sse_trading_days(test_start, test_end):
        # Run daily pipeline
        try:
            daily_result = run_daily(
                as_of=trading_day,
                root=None,
                bar_store=bar_store,
            )
        except Exception:
            _logger.warning(f"run_daily failed for {trading_day}", exc_info=True)
            continue

        # Extract weights from portfolio
        portfolio = daily_result.get("data", {}).get("portfolio")
        if portfolio is None:
            # No portfolio (e.g., signal_matrix failed), skip this day
            continue

        weights = {}
        for item in portfolio.get("target_weights", []):
            symbol = item.get("symbol")
            weight = item.get("weight", 0.0)
            if symbol and weight > 0:
                weights[symbol] = weight

        if not weights:
            # No positions
            continue

        # Compute daily return
        daily_ret = _compute_daily_return(
            weights=weights,
            as_of=trading_day,
            bar_store=bar_store,
            cost_bp=cost_bp,
        )

        if daily_ret is not None:
            daily_returns.append(daily_ret)
            cost_total_bp += cost_bp
            days_run += 1

    # Build metrics
    metrics = _build_window_metrics(daily_returns)
    metrics["warm_start"] = warm_start
    metrics["warm_end"] = (date.fromisoformat(test_start) - timedelta(days=1)).isoformat()
    metrics["test_start"] = test_start
    metrics["test_end"] = test_end
    metrics["days_run"] = days_run
    metrics["cost_total_bp"] = cost_total_bp

    return metrics


def run_walk_forward(
    start_date: str,
    end_date: str,
    warm_up_days: int = 180,
    test_window_days: int = 63,
    step_days: int = 21,
    cost_bp: float = 0.0,
    bar_store=None,
    thresholds: dict | None = None,
) -> dict:
    """Run walk-forward backtest.

    Args:
        start_date: "YYYY-MM-DD" start of backtest period
        end_date: "YYYY-MM-DD" end of backtest period
        warm_up_days: calendar days for warm-up window
        test_window_days: calendar days for test window
        step_days: calendar days to step forward
        cost_bp: transaction cost in basis points
        bar_store: bar_store port (required for bar queries)
        thresholds: custom threshold dict, uses _DEFAULT_THRESHOLDS if None

    Returns:
        Dict with verdict, failed_gates, windows, aggregate, params

    Raises:
        ValueError: if start_date > end_date or windows is empty
    """
    if not thresholds:
        thresholds = _DEFAULT_THRESHOLDS

    # Generate windows
    windows_spec = generate_windows(
        start_date=start_date,
        end_date=end_date,
        warm_up_days=warm_up_days,
        test_window_days=test_window_days,
        step_days=step_days,
    )

    if not windows_spec:
        raise ValueError(
            f"No windows generated for period {start_date} to {end_date} "
            f"with warm_up={warm_up_days}, test_window={test_window_days}, step={step_days}"
        )

    # Run each window
    windows_results = []
    for window_spec in windows_spec:
        try:
            result = _run_test_window(
                test_start=window_spec["test_start"],
                test_end=window_spec["test_end"],
                warm_start=window_spec["warm_start"],
                bar_store=bar_store,
                cost_bp=cost_bp,
            )
            windows_results.append(result)
        except Exception:
            _logger.warning(
                f"Window {window_spec['test_start']} to {window_spec['test_end']} failed",
                exc_info=True,
            )
            # Continue to next window
            continue

    if not windows_results:
        raise ValueError("No windows completed successfully")

    # Aggregate metrics
    aggregate = _aggregate_windows(windows_results)

    # Gate check
    gate_result = _gate_check(aggregate, thresholds)

    return {
        "verdict": gate_result["verdict"],
        "failed_gates": gate_result["failed_gates"],
        "windows": windows_results,
        "aggregate": aggregate,
        "params": {
            "start_date": start_date,
            "end_date": end_date,
            "warm_up_days": warm_up_days,
            "test_window_days": test_window_days,
            "step_days": step_days,
            "cost_bp": cost_bp,
        },
    }
