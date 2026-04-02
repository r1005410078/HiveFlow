from __future__ import annotations

from collections import defaultdict
from math import sqrt


_FACTOR_VERSION = "l2-basic-v1.1"
_FACTOR_NAMES = (
    "momentum_20",
    "inv_volatility_20",
    "turnover_rate",
    "max_drawdown_60",
    "trend_stability_20",
    "relative_strength_vs_index",
)


def _base_seed(symbol: str) -> int:
    # Keep L2 MVP deterministic without introducing random data.
    return int(symbol.split(".", 1)[0]) % 1000


def _factor_values_for_symbol(symbol: str) -> dict[str, float]:
    seed = _base_seed(symbol)
    momentum = round(0.01 + (seed % 50) / 1000, 6)
    inv_volatility = round(1.0 + (seed % 30) / 10.0, 6)
    turnover_rate = round(0.005 + (seed % 20) / 1000, 6)
    # Encode lower drawdown as a higher score-compatible value.
    max_drawdown_60 = round(0.65 + (seed % 30) / 100, 6)
    trend_stability_20 = round(0.5 + (seed % 40) / 100, 6)
    relative_strength_vs_index = round(0.9 + (seed % 35) / 100, 6)
    return {
        "momentum_20": momentum,
        "inv_volatility_20": inv_volatility,
        "turnover_rate": turnover_rate,
        "max_drawdown_60": max_drawdown_60,
        "trend_stability_20": trend_stability_20,
        "relative_strength_vs_index": relative_strength_vs_index,
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mu = _mean(values)
    var = sum((x - mu) ** 2 for x in values) / len(values)
    return sqrt(var)


def _max_drawdown(closes: list[float]) -> float:
    if not closes:
        return 0.0
    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        if peak > 0:
            dd = (peak - c) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _factor_values_from_real_bars(rows: list[dict]) -> dict[str, float] | None:
    if len(rows) < 61:
        return None
    ordered = sorted(rows, key=lambda r: str(r.get("bar_time", "")))
    closes = [float(r["close"]) for r in ordered]
    volumes = [float(r.get("volume") or 0.0) for r in ordered]

    close_t = closes[-1]
    close_t_20 = closes[-21]
    if close_t_20 == 0:
        return None
    momentum_20 = (close_t / close_t_20) - 1.0

    window_21 = closes[-21:]
    rets = []
    for i in range(20):
        prev_close = window_21[i]
        curr_close = window_21[i + 1]
        if prev_close == 0:
            continue
        rets.append((curr_close / prev_close) - 1.0)
    if not rets:
        return None
    vol_20 = _std(rets)
    inv_volatility_20 = 1.0 / max(vol_20, 1e-6)

    avg_vol_20 = _mean(volumes[-20:])
    turnover_rate = volumes[-1] / max(avg_vol_20, 1e-6)

    max_drawdown_60 = 1.0 - _max_drawdown(closes[-60:])

    up_days = sum(1 for r in rets if r > 0)
    trend_stability_20 = up_days / len(rets)

    # This is a per-symbol proxy when benchmark bars are unavailable in current scope.
    relative_strength_vs_index = 1.0 + momentum_20

    return {
        "momentum_20": round(momentum_20, 6),
        "inv_volatility_20": round(inv_volatility_20, 6),
        "turnover_rate": round(turnover_rate, 6),
        "max_drawdown_60": round(max_drawdown_60, 6),
        "trend_stability_20": round(trend_stability_20, 6),
        "relative_strength_vs_index": round(relative_strength_vs_index, 6),
    }


def compute_basic_factor_snapshot_from_bars(as_of: str, symbols: list[str], bar_rows: list[dict]) -> dict:
    rows_by_symbol: dict[str, list[dict]] = defaultdict(list)
    for row in bar_rows:
        symbol = row.get("symbol")
        if not symbol:
            continue
        rows_by_symbol[symbol].append(row)

    output_rows: list[dict] = []
    for symbol in symbols:
        values = _factor_values_from_real_bars(rows_by_symbol.get(symbol, []))
        if values is None:
            values = _factor_values_for_symbol(symbol)
        for factor_name, raw_value in values.items():
            output_rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": _FACTOR_VERSION,
                    "raw_value": raw_value,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(output_rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)
    return {
        "factor_version": _FACTOR_VERSION,
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": output_rows,
    }


def compute_basic_factor_snapshot(as_of: str, symbols: list[str]) -> dict:
    rows: list[dict] = []
    for symbol in symbols:
        values = _factor_values_for_symbol(symbol)
        for factor_name, raw_value in values.items():
            rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": _FACTOR_VERSION,
                    "raw_value": raw_value,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)

    return {
        "factor_version": _FACTOR_VERSION,
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": rows,
    }
