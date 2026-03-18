"""简化回测引擎（v1）。"""

from __future__ import annotations

import math
import pandas as pd
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
    curve: list[float]  # 从 1.0 开始的逐期权益值；无默认值


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
        curve=curve,
    )


def run_dynamic_backtest(
    prices: dict[str, list[PriceBar]],
    strategy: "BaseStrategy",
    rebalance_days: int = 7,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> "tuple[BacktestMetrics, dict[str, float]]":
    """动态再平衡回测：每隔 rebalance_days 天重新调用策略计算权重。

    - 每个块的起始时点之前的历史数据传给策略（无未来偏差）
    - 历史数据不足（策略抛异常）时降级为等权重
    - 交易成本（fee_bps + slippage_bps）在每个块的第一个周期扣除
    """
    from hiveflow.services.strategies.base import StrategyContext

    symbols = sorted(prices.keys())
    if not symbols:
        raise ValueError("没有可用的价格序列。")

    # 收集所有时间戳（跨 symbol 并集，排序）
    all_timestamps = sorted({
        bar.timestamp
        for sym in symbols
        for bar in prices[sym]
    })
    if len(all_timestamps) < 2:
        raise ValueError("价格序列至少需要 2 个时点。")

    # 构建 symbol → {timestamp: close} 快速查表
    bar_maps: dict[str, dict[str, float]] = {
        sym: {bar.timestamp: bar.close for bar in prices[sym]}
        for sym in symbols
    }

    # 按 rebalance_days 切分块
    blocks: list[tuple[str, list[str]]] = []
    for i in range(0, len(all_timestamps), rebalance_days):
        block_start = all_timestamps[i]
        block_ts = all_timestamps[i : i + rebalance_days]
        blocks.append((block_start, block_ts))

    per_trade_cost = (fee_bps + slippage_bps) / 10000.0
    equity = 1.0
    curve = [equity]
    all_returns: list[float] = []
    # 初始等权重（用于第一个块的 fallback）
    equal_weights: dict[str, float] = {sym: 1.0 / len(symbols) for sym in symbols}
    final_weights = dict(equal_weights)

    for block_start, block_ts in blocks:
        # 截取 block_start 之前的历史数据
        hist_ts = [ts for ts in all_timestamps if ts < block_start]

        # 构建 pd.DataFrame(index=range, columns=symbol)
        if hist_ts:
            df = pd.DataFrame(
                {sym: [bar_maps[sym].get(ts, float("nan")) for ts in hist_ts] for sym in symbols}
            )
        else:
            df = pd.DataFrame(columns=symbols)

        # 调用策略；失败时降级为等权重
        try:
            ctx = StrategyContext(
                prices=df,
                current_positions={},
                risk_signals={},
                params=strategy.params,
            )
            weights = strategy.compute_weights(ctx)
            final_weights = dict(weights)
        except Exception:
            weights = dict(equal_weights)
            final_weights = dict(equal_weights)

        # 模拟本块内逐日收益
        for ts_idx in range(1, len(block_ts)):
            prev_ts = block_ts[ts_idx - 1]
            curr_ts = block_ts[ts_idx]
            period_return = 0.0
            for sym in symbols:
                w = weights.get(sym, 0.0)
                if w == 0.0:
                    continue
                prev_close = bar_maps[sym].get(prev_ts)
                curr_close = bar_maps[sym].get(curr_ts)
                if prev_close is None or curr_close is None or prev_close <= 0:
                    continue
                period_return += w * (curr_close / prev_close - 1.0)
            # 每块首日扣除再平衡交易成本
            if ts_idx == 1:
                period_return -= per_trade_cost
            all_returns.append(period_return)
            equity *= 1.0 + period_return
            curve.append(equity)

    if not all_returns:
        raise ValueError("无法生成收益序列，请检查数据。")

    # 最大回撤
    peak = curve[0]
    max_drawdown = 0.0
    for value in curve:
        peak = max(peak, value)
        dd = value / peak - 1.0
        max_drawdown = min(max_drawdown, dd)

    # Sharpe（与 run_weighted_backtest 公式一致）
    mean_ret = sum(all_returns) / len(all_returns)
    variance = sum((r - mean_ret) ** 2 for r in all_returns) / max(len(all_returns) - 1, 1)
    std_ret = math.sqrt(variance)
    sharpe = mean_ret / std_ret * math.sqrt(len(all_returns)) if std_ret > 0 else 0.0

    return (
        BacktestMetrics(
            periods=len(all_returns),
            total_return=equity - 1.0,
            max_drawdown=max_drawdown,
            sharpe=sharpe,
            curve=curve,
        ),
        final_weights,
    )


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
