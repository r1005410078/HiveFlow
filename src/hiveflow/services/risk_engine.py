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


def compute_volatility(prices: dict[str, list[PriceBar]]) -> list[AssetVolatility]:
    """计算各资产日收益率的样本标准差（ddof=1），年化（× sqrt(365)）。

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
        annual_vol = daily_vol * math.sqrt(365)
        results.append(AssetVolatility(
            symbol=symbol,
            annual_vol=annual_vol,
            daily_vol=daily_vol,
            periods=len(sorted_bars),
        ))
    return sorted(results, key=lambda x: x.annual_vol, reverse=True)


def classify_priority_from_risk(risk_waterline: str) -> str:
    """将风险水位映射为处理优先级。"""
    level = risk_waterline.strip().lower()
    if level in {RiskWaterline.HIGH, RiskWaterline.EXTREME}:
        return PriorityLevel.HIGH
    if level in {RiskWaterline.MEDIUM, RiskWaterline.MID}:
        return PriorityLevel.MEDIUM
    return PriorityLevel.LOW


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
