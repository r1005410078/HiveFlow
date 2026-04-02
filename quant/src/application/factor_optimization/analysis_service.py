from __future__ import annotations

from collections import defaultdict
from math import sqrt

from application.factor.basic_factor_service import compute_basic_factor_snapshot_from_bars


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mu = _mean(values)
    var = sum((x - mu) ** 2 for x in values) / len(values)
    return sqrt(var)


def _rank(values: list[float]) -> list[float]:
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def _pearson(x: list[float], y: list[float]) -> float:
    if len(x) != len(y) or len(x) < 2:
        return 0.0
    mx = _mean(x)
    my = _mean(y)
    num = sum((a - mx) * (b - my) for a, b in zip(x, y, strict=False))
    den = sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
    if den == 0:
        return 0.0
    return num / den


def _spearman(x: list[float], y: list[float]) -> float:
    return _pearson(_rank(x), _rank(y))


def _max_drawdown(series: list[float]) -> float:
    if not series:
        return 0.0
    peak = series[0]
    max_dd = 0.0
    for value in series:
        if value > peak:
            peak = value
        if peak != 0:
            dd = (peak - value) / peak
            if dd > max_dd:
                max_dd = dd
    return max_dd


def _group_bars_by_symbol(rows: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        symbol = row.get("symbol")
        if symbol:
            grouped[symbol].append(row)
    for symbol, bars in grouped.items():
        grouped[symbol] = sorted(bars, key=lambda r: str(r.get("bar_time", "")))
    return grouped


def _forward_returns(grouped: dict[str, list[dict]], forward_days: int) -> dict[str, float]:
    out: dict[str, float] = {}
    for symbol, bars in grouped.items():
        closes = [float(item.get("close") or 0.0) for item in bars]
        if len(closes) <= forward_days:
            continue
        prev = closes[-forward_days - 1]
        curr = closes[-1]
        if prev == 0:
            continue
        out[symbol] = (curr / prev) - 1.0
    return out


def analyze_factors(bars: list[dict], factor_names: list[str], forward_days: int = 1) -> dict:
    grouped = _group_bars_by_symbol(bars)
    symbols = sorted(grouped.keys())
    if not symbols:
        return {
            "factor_health": [],
            "correlation_matrix": {},
            "coverage": {"symbols": 0, "bars": 0},
        }

    as_of = max(str(row.get("bar_time", ""))[:10] for row in bars if row.get("bar_time"))
    snapshot = compute_basic_factor_snapshot_from_bars(as_of=as_of, symbols=symbols, bar_rows=bars)

    returns = _forward_returns(grouped, forward_days=forward_days)
    if not returns:
        return {
            "factor_health": [
                {
                    "factor_name": name,
                    "ic": 0.0,
                    "sharpe": 0.0,
                    "max_drawdown": 0.0,
                }
                for name in factor_names
            ],
            "correlation_matrix": {
                left: {right: 1.0 if left == right else 0.0 for right in factor_names}
                for left in factor_names
            },
            "coverage": {"symbols": len(symbols), "bars": len(bars)},
        }

    factor_values_by_symbol: dict[str, dict[str, float]] = {s: {} for s in symbols}
    for row in snapshot.get("rows", []):
        factor_name = row.get("factor_name")
        symbol = row.get("symbol")
        if factor_name in factor_names and symbol in factor_values_by_symbol:
            factor_values_by_symbol[symbol][factor_name] = float(row.get("raw_value") or 0.0)

    factor_health: list[dict] = []
    for factor_name in factor_names:
        xs: list[float] = []
        ys: list[float] = []
        signal_returns: list[float] = []
        for symbol in symbols:
            if symbol not in returns:
                continue
            x = factor_values_by_symbol[symbol].get(factor_name)
            if x is None:
                continue
            y = returns[symbol]
            xs.append(x)
            ys.append(y)
            signal_returns.append(x * y)

        ic = round(_spearman(xs, ys), 6) if xs else 0.0
        sharpe = 0.0
        if signal_returns:
            denom = _std(signal_returns)
            sharpe = round(_mean(signal_returns) / denom, 6) if denom > 0 else 0.0

        cum = []
        total = 1.0
        for v in signal_returns:
            total *= 1.0 + v
            cum.append(total)
        max_dd = round(_max_drawdown(cum), 6)

        factor_health.append(
            {
                "factor_name": factor_name,
                "ic": ic,
                "sharpe": sharpe,
                "max_drawdown": max_dd,
            }
        )

    correlation_matrix: dict[str, dict[str, float]] = {}
    for left in factor_names:
        correlation_matrix[left] = {}
        left_vals = [factor_values_by_symbol[s].get(left, 0.0) for s in symbols]
        for right in factor_names:
            right_vals = [factor_values_by_symbol[s].get(right, 0.0) for s in symbols]
            corr = _pearson(left_vals, right_vals)
            correlation_matrix[left][right] = round(corr, 6)

    return {
        "factor_health": factor_health,
        "correlation_matrix": correlation_matrix,
        "coverage": {"symbols": len(symbols), "bars": len(bars)},
    }
