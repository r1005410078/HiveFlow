"""简化回测引擎（v1）。"""

from __future__ import annotations

import math
from csv import DictReader
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PriceBar:
    """行情 K 线数据。"""

    symbol: str
    timestamp: str
    close: float


@dataclass(frozen=True)
class BacktestMetrics:
    """回测指标结果。"""

    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float


def load_close_prices(file: Path) -> dict[str, list[PriceBar]]:
    """从 CSV 读取 close 序列。"""
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("价格 CSV 文件不存在。")
    result: dict[str, list[PriceBar]] = {}
    with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = DictReader(csv_file)
        for row in reader:
            symbol = (row.get("symbol") or "").strip().upper()
            timestamp = (row.get("timestamp") or "").strip()
            if not symbol or not timestamp:
                continue
            close = float(row.get("close") or 0.0)
            result.setdefault(symbol, []).append(
                PriceBar(symbol=symbol, timestamp=timestamp, close=close)
            )
    for symbol in result:
        result[symbol] = sorted(result[symbol], key=lambda item: item.timestamp)
    return result


def run_weighted_backtest(
    prices: dict[str, list[PriceBar]],
    weights: dict[str, float],
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestMetrics:
    """基于目标权重的简化组合回测。"""
    symbols = [symbol for symbol in sorted(weights) if symbol in prices and len(prices[symbol]) >= 2]
    if not symbols:
        raise ValueError("缺少可回测的价格序列（至少需要两个时点 close）。")

    min_len = min(len(prices[symbol]) for symbol in symbols)
    equity = 1.0
    curve = [equity]
    returns: list[float] = []

    per_trade_cost = (fee_bps + slippage_bps) / 10000.0
    for idx in range(1, min_len):
        period_return = 0.0
        for symbol in symbols:
            prev_close = prices[symbol][idx - 1].close
            curr_close = prices[symbol][idx].close
            if prev_close <= 0:
                continue
            symbol_ret = curr_close / prev_close - 1.0
            period_return += weights[symbol] * symbol_ret
        period_return -= per_trade_cost
        returns.append(period_return)
        equity *= 1.0 + period_return
        curve.append(equity)

    peak = curve[0]
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        drawdown = value / peak - 1.0
        max_drawdown = min(max_drawdown, drawdown)

    mean_ret = sum(returns) / len(returns)
    variance = sum((item - mean_ret) ** 2 for item in returns) / max(len(returns) - 1, 1)
    std_ret = math.sqrt(variance)
    sharpe = mean_ret / std_ret * math.sqrt(len(returns)) if std_ret > 0 else 0.0
    return BacktestMetrics(
        periods=len(returns),
        total_return=equity - 1.0,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
    )


def run_dynamic_backtest(
    prices: dict[str, list[PriceBar]],
    strategy,
    rebalance_interval: int = 1,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestMetrics:
    """基于动态策略的组合回测（动态再平衡）。待实现。"""
    raise NotImplementedError("run_dynamic_backtest 尚未实现（Task 2）。")


def load_close_prices_from_db(
    symbols: list[str],
    settings=None,
) -> dict[str, list[PriceBar]]:
    """从 DB 的 MarketBar 表读取 close 序列。"""
    from sqlmodel import select
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar

    create_all_tables(settings)
    result: dict[str, list[PriceBar]] = {}
    with get_session(settings) as session:
        for symbol in symbols:
            rows = session.exec(
                select(MarketBar)
                .where(MarketBar.symbol == symbol)
                .order_by(MarketBar.timestamp)
            ).all()
            if not rows:
                continue
            result[symbol] = [
                PriceBar(
                    symbol=r.symbol,
                    timestamp=r.timestamp.isoformat(),
                    close=r.close,
                )
                for r in rows
            ]
    return result
