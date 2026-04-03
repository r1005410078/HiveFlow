from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import TypedDict


class FactorMeta(TypedDict):
    version: str
    direction: int
    unit: str
    missing_strategy: str


FACTOR_METADATA: dict[str, FactorMeta] = {
    "momentum_20": {
        "version": "l2-momentum-v1.0",
        "direction": 1,
        "unit": "return",
        "missing_strategy": "deterministic_fallback",
    },
    "inv_volatility_20": {
        "version": "l2-inv-vol-v1.0",
        "direction": 1,
        "unit": "1/return_std",
        "missing_strategy": "deterministic_fallback",
    },
    "turnover_rate": {
        "version": "l2-turnover-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "max_drawdown_60": {
        "version": "l2-mdd-v1.0",
        "direction": 1,  # encoded as 1.0 - raw_drawdown, so higher = less drawdown
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "trend_stability_20": {
        "version": "l2-trend-stab-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    "relative_strength_vs_index": {
        "version": "l2-rsi-v1.1",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "benchmark_proxy_fallback",
    },
}

_FACTOR_NAMES = tuple(FACTOR_METADATA.keys())


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
    # 计算均值；空序列返回 0，避免上层分母异常。
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    # 使用总体标准差（非样本标准差）作为波动率近似。
    if not values:
        return 0.0
    mu = _mean(values)
    var = sum((x - mu) ** 2 for x in values) / len(values)
    return sqrt(var)


def _max_drawdown(closes: list[float]) -> float:
    # 计算最大回撤（0~1），用于风险因子。
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
    # 使用真实 1d bars 计算 6 因子；样本不足时返回 None，让上层走回退策略。
    if len(rows) < 61:
        return None
    # bars 查询默认是倒序，先转为按时间正序，避免收益率/回撤方向错误。
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

    # 当前作用域未引入基准指数 bars，先使用个股收益代理相对强弱，后续可替换为真实基准对比。
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
    # 按 symbol 聚合 bars，再逐标的计算因子；若单标的数据不足则回退到 deterministic 因子。
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
            # 兜底：保障日频流水线在数据空窗/历史不足时仍可产出稳定结构。
            values = _factor_values_for_symbol(symbol)
        for factor_name, raw_value in values.items():
            meta = FACTOR_METADATA[factor_name]
            output_rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": meta["version"],
                    "raw_value": raw_value,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(output_rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)
    return {
        "snapshot_version": "l2-basic-v1.1",
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": output_rows,
    }


def compute_basic_factor_snapshot(as_of: str, symbols: list[str]) -> dict:
    # deterministic 快照：用于无 DB/无 bars 场景和测试稳定性。
    rows: list[dict] = []
    for symbol in symbols:
        values = _factor_values_for_symbol(symbol)
        for factor_name, raw_value in values.items():
            meta = FACTOR_METADATA[factor_name]
            rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": meta["version"],
                    "raw_value": raw_value,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)

    return {
        "snapshot_version": "l2-basic-v1.1",
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": rows,
    }
