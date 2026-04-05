from __future__ import annotations

import logging
from collections import defaultdict
from math import sqrt
from typing import TypedDict


class FactorMeta(TypedDict):
    version: str
    direction: int
    unit: str
    missing_strategy: str


# 「因子」在本项目中的含义（与 L2 横截面打分、L3 信号矩阵对齐）：
# - 因子 = 在每只标的、每个 as_of 上可重复计算的一维特征值（如动量、波动）；不是模型里的权重系数。
# - 权重 / 打分系数（如 l2_decision_service 的 profile weights）属于「参数」，随策略版本变更，与单标的观测的因子值不同。
# - 矩阵视角：行≈标的，列≈因子名，元素=该标的在该因子上的 raw_value；再经加权、归一化或非线性变换得到得分向量，用于排序与多空（与「每列一个因子」一致，而非「任意单格即一个独立因子」）。
#
# L2 六因子注册表：版本、经济方向、量纲、缺失时的降级策略（与快照行里的 factor_version 等一致）。
# direction=1 表示 raw_value 越大越「好」，与后续横截面打分方向一致。
FACTOR_METADATA: dict[str, FactorMeta] = {
    # 20 日动量：最新收盘相对 20 个交易日前的区间收益率 (P_t / P_{t-20} - 1)。
    # 例：前日（20 交易日前）100 元、今日 105 元 → +5%；今日 95 元 → -5%。
    # 常见作用：① 中期趋势/动量，横截面上比谁「这一段涨得多」；② 与价值、质量等因子或多空组合；③ 刻画约 20 日方向，非单日涨跌，不宜单独当买卖信号。
    "momentum_20": {
        "version": "l2-momentum-v1.0",
        "direction": 1,
        "unit": "return",
        "missing_strategy": "deterministic_fallback",
    },
    # 20 日波动率倒数：近 20 日日收益标准差的倒数，偏好低波动（分母下限 1e-6 防止除零）。
    # 取最近大约 20 个交易日，每天都有涨跌幅（相对前一天收盘的百分比变化）。
    # 这些涨跌忽大忽小：有的票每天上下晃得厉害，有的票每天变化很平。
    # 用一个数概括「晃得厉害不大」：标准差（代码里对 20 个日收益率算的那个）。
    # 晃得凶 → 标准差大
    # 很平稳 → 标准差小
    # 因子的设定是：数值越大 = 越好（direction = 1）。
    # 若直接用「标准差」当因子：
    # 波动小 → 标准差小 → 分数反而低（和「偏好低波动」矛盾）。
    # 所以不直接用标准差，而用 1 ÷ 标准差：
    # 波动小 → 标准差小 → 除以一个小数 → 得到大的数 → 因子分高
    # 波动大 → 标准差大 → 除以一个大数 → 得到小的数 → 因子分低
    # 一句话：「波动率倒数」= 把「越稳越好」变成「数越大越好」的一种写法。
    # 分母不能是 0，所以代码里用 max(标准差, 1e-6)，避免除零。
    # 常见作用：① 偏好日涨跌更「稳」的标的（低波类特征）；② 与动量并行时常作波动/路径维度；③ 与最大回撤不同维，但都影响持有体验。

    "inv_volatility_20": {
        "version": "l2-inv-vol-v1.0",
        "direction": 1,
        "unit": "1/return_std",
        "missing_strategy": "deterministic_fallback",
    },
    # 成交额活跃：当日成交量 / 近 20 日均量，衡量相对放量（偏好高换手/活跃）。
    # 例：今日量 200 万股、近 20 日均量 100 万股 → 比值 2.0（相对放量一倍）。
    # 大白话：不比别的票谁量大，只看「今天比自己最近 20 天平常水平热闹多少倍」。
    # 常见作用：① 相对放量、市场参与度异常（消息/题材常伴随）；② 量价类规则的辅助特征；③ 实盘流动性常另设「绝对成交额/量」门槛，本因子是相对比、侧重形态而非能否成交。
    "turnover_rate": {
        "version": "l2-turnover-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    # 60 日回撤形态：1 - 区间最大回撤，raw 越大表示回撤越小（与「低风险」同向）。
    # 例：60 日内从高点最多跌到 85%（最大回撤 0.15）→ raw≈1-0.15=0.85；若几乎未回撤 → raw 接近 1。
    # 大白话：约 60 天里从「这段最高价」往下最多摔多狠；摔得少 raw 高，几乎不深跌 raw 接近 1。
    # 常见作用：① 中期回撤与下行风险画像；② 与动量互补（涨得多但回撤深会被压低）；③ 组合层控制净值波动、避雷「尖顶深坑」路径的参考维。
    "max_drawdown_60": {
        "version": "l2-mdd-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    # 20 日趋势稳定性：近 20 日正收益日占比，偏好上涨日多的标的。
    # 例：20 个交易日里 12 天收涨、8 天收跌 → 12/20=0.6；天天涨则 1.0。
    # 大白话：数的是「涨的日子多不多」，不太看单日涨跌幅度有多大。
    # 常见作用：① 区分「碎步涨」与「大阴大阳但区间收益一般」；② 与区间动量同看：收益接近时偏好上涨日更连贯；③ 路径质量/胜率感，非幅度因子。
    "trend_stability_20": {
        "version": "l2-trend-stab-v1.0",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "deterministic_fallback",
    },
    # 相对基准强弱：有指数 bars 时用 20 日超额收益式相对强弱；无基准时降级为 1 + momentum_20 代理。
    # 例（有基准）：个股 20 日涨 +5%、指数涨 +2% → (1.05/1.02)-1≈+2.9% 的相对强弱。
    # 例（无基准代理）：20 日动量 +0.03 → 代理值 1+0.03=1.03。
    # 大白话（有基准）：同样约 20 天，这只票比大盘多赚还是少赚。
    # 大白话（无基准）：没有指数数据时用 1+动量顶一下，不是真的「相对大盘强弱」。
    # 常见作用：① 有基准时：跑赢/跑输指数的中期相对强弱；② 风格、行业 β 的粗粒度刻画之一；③ 无基准时代理仅降级填充，勿当真实超额。
    "relative_strength_vs_index": {
        "version": "l2-rsi-v1.1",
        "direction": 1,
        "unit": "ratio",
        "missing_strategy": "benchmark_proxy_fallback",
    },
}

_FACTOR_NAMES = tuple(FACTOR_METADATA.keys())

_logger = logging.getLogger(__name__)


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


def compute_raw_factor_values_from_bar_rows(rows: list[dict]) -> dict[str, float] | None:
    """单标的、按 ``bar_time`` 排序的 1d bars，计算 6 因子原始值（与快照/日频共用公式）。

    不足 61 根 K 线时返回 ``None``。仅使用传入窗口内数据，适用于 PIT 与滚动计算。
    """
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


def _relative_strength_from_benchmark(
    symbol_closes: list[float],
    benchmark_rows: list[dict],
) -> float | None:
    """Returns real relative strength vs benchmark. Returns None if symbol or benchmark has < 21 bars."""
    if len(symbol_closes) < 21:
        return None
    ordered = sorted(benchmark_rows, key=lambda r: str(r.get("bar_time", "")))
    b_closes = [float(r["close"]) for r in ordered]
    if len(b_closes) < 21:
        return None
    b_t = b_closes[-1]
    b_t20 = b_closes[-21]
    if b_t20 == 0:
        return None
    benchmark_ret_20 = (b_t / b_t20) - 1.0
    symbol_t = symbol_closes[-1]
    symbol_t20 = symbol_closes[-21]
    if symbol_t20 == 0:
        return None
    symbol_ret_20 = (symbol_t / symbol_t20) - 1.0
    return (1.0 + symbol_ret_20) / (1.0 + benchmark_ret_20) - 1.0


def _compute_stability_metrics(
    rows: list[dict],
    factor_names: tuple,
    historical_baselines: dict[str, dict] | None,
) -> list[dict]:
    values_by_factor: dict[str, list[float]] = defaultdict(list)
    real_count_by_factor: dict[str, int] = defaultdict(int)
    fallback_count_by_factor: dict[str, int] = defaultdict(int)

    for row in rows:
        fn = row["factor_name"]
        values_by_factor[fn].append(row["raw_value"])
        if row.get("source") == "real":
            real_count_by_factor[fn] += 1
        else:
            fallback_count_by_factor[fn] += 1

    total_symbols = (
        (real_count_by_factor.get(factor_names[0], 0) + fallback_count_by_factor.get(factor_names[0], 0))
        if factor_names
        else 0
    )

    if historical_baselines:
        known_factor_set = set(factor_names)
        for key in historical_baselines:
            if key not in known_factor_set:
                _logger.warning(
                    "historical_baselines contains unknown factor key %r; skipping drift for it", key
                )

    result = []
    for fn in factor_names:
        vals = values_by_factor.get(fn, [])
        real_c = real_count_by_factor.get(fn, 0)
        fallback_c = fallback_count_by_factor.get(fn, 0)
        coverage = round(real_c / total_symbols, 4) if total_symbols > 0 else 0.0
        mean_v = round(_mean(vals), 6) if vals else 0.0
        std_v = round(_std(vals), 6) if vals else 0.0

        drift_flag = None
        drift_z = None
        if historical_baselines and fn in historical_baselines:
            baseline = historical_baselines[fn]
            b_mean = float(baseline.get("mean", 0.0))
            b_std = float(baseline.get("std", 1e-6))
            drift_z = round((mean_v - b_mean) / max(b_std, 1e-6), 4)
            drift_flag = abs(drift_z) > 2.0

        result.append(
            {
                "factor_name": fn,
                "factor_version": FACTOR_METADATA[fn]["version"],
                "coverage_rate": coverage,
                "real_count": real_c,
                "fallback_count": fallback_c,
                "mean_value": mean_v,
                "std_value": std_v,
                "drift_flag": drift_flag,
                "drift_z_score": drift_z,
            }
        )
    return result


def compute_basic_factor_snapshot_from_bars(
    as_of: str,
    symbols: list[str],
    bar_rows: list[dict],
    benchmark_rows: list[dict] | None = None,
    historical_baselines: dict[str, dict] | None = None,  # used in Task 4: stability metrics
) -> dict:
    # 按 symbol 聚合 bars，再逐标的计算因子；若单标的数据不足则回退到 deterministic 因子。
    rows_by_symbol: dict[str, list[dict]] = defaultdict(list)
    for row in bar_rows:
        symbol = row.get("symbol")
        if not symbol:
            continue
        rows_by_symbol[symbol].append(row)

    output_rows: list[dict] = []
    for symbol in symbols:
        real_values = compute_raw_factor_values_from_bar_rows(rows_by_symbol.get(symbol, []))
        if real_values is None:
            # 兜底：保障日频流水线在数据空窗/历史不足时仍可产出稳定结构。
            values = _factor_values_for_symbol(symbol)
            default_source = "deterministic_fallback"
            rs_used_real_benchmark = False
        else:
            values = real_values
            default_source = "real"
            # Try to compute real relative strength vs benchmark
            rs_used_real_benchmark = False
            if benchmark_rows is not None:
                ordered_sym = sorted(
                    rows_by_symbol.get(symbol, []),
                    key=lambda r: str(r.get("bar_time", "")),
                )
                sym_closes = [float(r["close"]) for r in ordered_sym]
                rs_real = _relative_strength_from_benchmark(sym_closes, benchmark_rows)
                if rs_real is not None:
                    values["relative_strength_vs_index"] = round(rs_real, 6)
                    rs_used_real_benchmark = True

        for factor_name, raw_value in values.items():
            meta = FACTOR_METADATA[factor_name]
            if factor_name == "relative_strength_vs_index" and default_source == "real" and not rs_used_real_benchmark:
                row_source = "benchmark_proxy_fallback"
            else:
                row_source = default_source
            output_rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": meta["version"],
                    "raw_value": raw_value,
                    "direction": meta["direction"],
                    "unit": meta["unit"],
                    "missing_strategy": meta["missing_strategy"],
                    "source": row_source,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(output_rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)
    stability_metrics = _compute_stability_metrics(
        rows=output_rows,
        factor_names=_FACTOR_NAMES,
        historical_baselines=historical_baselines,
    )
    return {
        "snapshot_version": "l2-basic-v1.1",
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": output_rows,
        "stability_metrics": stability_metrics,
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
                    "direction": meta["direction"],
                    "unit": meta["unit"],
                    "missing_strategy": meta["missing_strategy"],
                    "source": "deterministic_fallback",
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)

    stability_metrics = _compute_stability_metrics(
        rows=rows,
        factor_names=_FACTOR_NAMES,
        historical_baselines=None,
    )
    return {
        "snapshot_version": "l2-basic-v1.1",
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": rows,
        "stability_metrics": stability_metrics,
    }
