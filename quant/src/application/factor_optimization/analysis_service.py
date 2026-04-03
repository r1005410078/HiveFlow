from __future__ import annotations

from collections import defaultdict
from math import sqrt

from application.factor.basic_factor_service import compute_raw_factor_values_from_bar_rows


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
    for symbol, row_list in grouped.items():
        grouped[symbol] = sorted(row_list, key=lambda r: str(r.get("bar_time", "")))
    return grouped


def _pit_factor_and_forward(
    sorted_bars: list[dict],
    forward_days: int,
) -> tuple[dict[str, float] | None, float | None]:
    """锚定日 T = 倒数第 forward_days 根 K 线：因子仅用 <=T 的 bar；标签为 close[-1]/close[T]-1。"""
    n = len(sorted_bars)
    min_n = 61 + forward_days
    if n < min_n:
        return None, None
    anchor_idx = n - 1 - forward_days
    fac_rows = sorted_bars[: anchor_idx + 1]
    vals = compute_raw_factor_values_from_bar_rows(fac_rows)
    if vals is None:
        return None, None
    closes = [float(r.get("close") or 0.0) for r in sorted_bars]
    denom = closes[anchor_idx]
    if denom == 0:
        return None, None
    forward_ret = (closes[-1] / denom) - 1.0
    return vals, forward_ret


def analyze_factors(bars: list[dict], factor_names: list[str], forward_days: int = 1) -> dict:
    """因子优化建议用分析（**advice-only**）：IC / Sharpe 基于 PIT 截面，**非**替代 L2 日频快照。

    每标的至少需要 ``61 + forward_days`` 根日线；不足则跳过该标的。
    """
    grouped = _group_bars_by_symbol(bars)
    symbols = sorted(grouped.keys())
    if not symbols:
        return {
            "factor_health": [],
            "correlation_matrix": {},
            "coverage": {"symbols": 0, "bars": 0},
        }

    pit_factors: dict[str, dict[str, float]] = {}
    pit_forwards: dict[str, float] = {}
    for symbol in symbols:
        vals, fwd = _pit_factor_and_forward(grouped[symbol], forward_days=forward_days)
        if vals is not None and fwd is not None:
            pit_factors[symbol] = vals
            pit_forwards[symbol] = fwd

    pit_symbols = sorted(pit_factors.keys())

    if not pit_symbols:
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

    factor_health: list[dict] = []
    for factor_name in factor_names:
        xs: list[float] = []
        ys: list[float] = []
        signal_returns: list[float] = []
        for symbol in pit_symbols:
            x = pit_factors[symbol].get(factor_name)
            if x is None:
                continue
            y = pit_forwards[symbol]
            xs.append(float(x))
            ys.append(float(y))
            signal_returns.append(float(x) * float(y))

        ic = round(_spearman(xs, ys), 6) if xs else 0.0
        sharpe = 0.0
        if signal_returns:
            denom_sr = _std(signal_returns)
            sharpe = round(_mean(signal_returns) / denom_sr, 6) if denom_sr > 0 else 0.0

        cum: list[float] = []
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
        left_vals = [float(pit_factors[s].get(left, 0.0)) for s in pit_symbols]
        for right in factor_names:
            right_vals = [float(pit_factors[s].get(right, 0.0)) for s in pit_symbols]
            corr = _pearson(left_vals, right_vals)
            correlation_matrix[left][right] = round(corr, 6)

    return {
        "factor_health": factor_health,
        "correlation_matrix": correlation_matrix,
        "coverage": {"symbols": len(symbols), "bars": len(bars)},
    }
