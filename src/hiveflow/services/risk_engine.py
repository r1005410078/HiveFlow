"""风险分析引擎——纯计算，无 DB 依赖。"""
from __future__ import annotations

import math
from dataclasses import dataclass

from hiveflow.domain.value_objects import PriorityLevel
from hiveflow.domain.value_objects import RiskWaterline
from hiveflow.domain.market_data import MarketBar
from hiveflow.services.backtest_engine import PriceBar


@dataclass(frozen=True)
class AssetVolatility:
    symbol: str
    annual_vol: float   # 年化标准差（daily_vol × sqrt(365)）
    daily_vol: float    # 日标准差（样本标准差，ddof=1）
    periods: int        # 价格条数（非收益率条数）


@dataclass(frozen=True)
class CorrelationMatrix:
    symbols: list[str]
    matrix: list[list[float]]   # n×n Pearson 矩阵；对角线 == 1.0；不足数据时填 nan


@dataclass(frozen=True)
class AssetDrawdown:
    symbol: str
    max_drawdown: float   # 非正数：有回撤时为负（如 -0.85），无回撤时为 0.0
    periods: int          # 价格条数


def compute_volatility(
    prices: dict[str, list[PriceBar]],
    annualization_factor: int = 365,
) -> list[AssetVolatility]:
    """计算各资产日收益率的样本标准差（ddof=1），年化（× sqrt(annualization_factor)）。

    - 数据点 < 2 的资产跳过（不报错）
    - 结果按 annual_vol 降序排列
    """
    results: list[AssetVolatility] = []
    for symbol, bars in prices.items():
        if len(bars) < 2:
            continue
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        returns = [
            sorted_bars[i].close / sorted_bars[i - 1].close - 1.0
            for i in range(1, len(sorted_bars))
            if sorted_bars[i - 1].close > 0
        ]
        if not returns:
            continue
        n = len(returns)
        mean_r = sum(returns) / n
        variance = sum((r - mean_r) ** 2 for r in returns) / max(n - 1, 1)
        daily_vol = math.sqrt(variance)
        annual_vol = daily_vol * math.sqrt(annualization_factor)
        results.append(AssetVolatility(
            symbol=symbol,
            annual_vol=annual_vol,
            daily_vol=daily_vol,
            periods=len(sorted_bars),
        ))
    return sorted(results, key=lambda x: x.annual_vol, reverse=True)


def compute_correlation(prices: dict[str, list[PriceBar]]) -> CorrelationMatrix:
    """计算资产两两之间的 Pearson 相关系数矩阵。

    - 对齐到各对资产的共同收益率时间戳
    - 共同点 < 2 → 对应位置填 float('nan')
    - symbols 按字母序排列；matrix[i][i] == 1.0
    """
    symbols = sorted(prices.keys())

    # 构建各资产收益率 dict: timestamp → return
    returns_map: dict[str, dict[str, float]] = {}
    for symbol, bars in prices.items():
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        sym_returns: dict[str, float] = {}
        for i in range(1, len(sorted_bars)):
            if sorted_bars[i - 1].close > 0:
                r = sorted_bars[i].close / sorted_bars[i - 1].close - 1.0
                sym_returns[sorted_bars[i].timestamp] = r
        returns_map[symbol] = sym_returns

    n = len(symbols)
    matrix: list[list[float]] = [[0.0] * n for _ in range(n)]

    for i, si in enumerate(symbols):
        for j, sj in enumerate(symbols):
            if i == j:
                matrix[i][j] = 1.0
                continue
            common_ts = sorted(set(returns_map[si]) & set(returns_map[sj]))
            if len(common_ts) < 2:
                matrix[i][j] = float("nan")
                continue
            xs = [returns_map[si][ts] for ts in common_ts]
            ys = [returns_map[sj][ts] for ts in common_ts]
            n_c = len(xs)
            mean_x = sum(xs) / n_c
            mean_y = sum(ys) / n_c
            cov = sum((xs[k] - mean_x) * (ys[k] - mean_y) for k in range(n_c))
            var_x = sum((xs[k] - mean_x) ** 2 for k in range(n_c))
            var_y = sum((ys[k] - mean_y) ** 2 for k in range(n_c))
            if var_x == 0 or var_y == 0:
                matrix[i][j] = float("nan")
            else:
                matrix[i][j] = cov / math.sqrt(var_x * var_y)

    return CorrelationMatrix(symbols=symbols, matrix=matrix)


def classify_priority_from_risk(risk_waterline: str) -> str:
    """将风险水位映射为处理优先级。"""
    level = risk_waterline.strip().lower()
    if level in {RiskWaterline.HIGH, RiskWaterline.EXTREME}:
        return PriorityLevel.HIGH
    if level in {RiskWaterline.MEDIUM, RiskWaterline.MID}:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


def compute_drawdown(prices: dict[str, list[PriceBar]]) -> list[AssetDrawdown]:
    """计算各资产在给定价格序列中的最大回撤（从峰值到谷值）。

    - max_drawdown 为非正数（回撤为负，无回撤为 0.0）
    - 结果按 max_drawdown 升序（最大亏损在前）
    """
    results: list[AssetDrawdown] = []
    for symbol, bars in prices.items():
        if not bars:
            continue
        sorted_bars = sorted(bars, key=lambda b: b.timestamp)
        closes = [b.close for b in sorted_bars]
        peak = closes[0]
        max_dd = 0.0
        for c in closes:
            if c > peak:
                peak = c
            if peak > 0:
                dd = c / peak - 1.0
                if dd < max_dd:
                    max_dd = dd
        results.append(AssetDrawdown(
            symbol=symbol,
            max_drawdown=max_dd,
            periods=len(sorted_bars),
        ))
    return sorted(results, key=lambda x: x.max_drawdown)


def compute_portfolio_risk(curve: list[float], annualization_factor: int = 365) -> dict:
    """从 equity curve 派生组合级风险指标。

    返回: annual_vol, win_rate（正收益期比例）, calmar_ratio（总收益/|MDD|）

    - len(curve) < 2 → 抛 ValueError
    - MDD == 0 时 calmar_ratio 为 float('inf')
    """
    if len(curve) < 2:
        raise ValueError("equity curve 至少需要 2 个数据点。")
    returns = [curve[i] / curve[i - 1] - 1.0 for i in range(1, len(curve))]
    n = len(returns)
    mean_r = sum(returns) / n
    variance = sum((r - mean_r) ** 2 for r in returns) / max(n - 1, 1)
    daily_vol = math.sqrt(variance)
    annual_vol = daily_vol * math.sqrt(annualization_factor)
    win_rate = sum(1 for r in returns if r > 0) / n
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    total_return = curve[-1] / curve[0] - 1.0
    calmar = total_return / abs(max_dd) if max_dd != 0.0 else float("inf")
    return {
        "annual_vol": annual_vol,
        "win_rate": win_rate,
        "calmar_ratio": calmar,
    }


def calculate_max_drawdown(bars: list[MarketBar]) -> float:
    """计算最大回撤（负数或 0）。以历史最高收盘价为基准。"""
    if len(bars) < 2:
        return 0.0
    closes = [b.close for b in bars]
    peak = closes[0]
    max_dd = 0.0
    for c in closes[1:]:
        if c > peak:
            peak = c
        dd = (c - peak) / peak
        if dd < max_dd:
            max_dd = dd
    return max_dd
