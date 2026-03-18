"""动态回测测试套件。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.application.backtest import list_backtest_results, run_quant_backtest
from hiveflow.domain.backtests import BacktestResult
from hiveflow.db import create_all_tables, get_session
from hiveflow.services.backtest_engine import PriceBar, run_dynamic_backtest
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy
from hiveflow.services.strategies.momentum import MomentumStrategy


# ─── 辅助函数 ───────────────────────────────────────────────────────────────

def _make_bars(symbol: str, closes: list[float], base: str = "2026-01-") -> list[PriceBar]:
    """构造 PriceBar 列表，时间戳格式 2026-01-01T00:00:00Z 等。"""
    bars = []
    for i, close in enumerate(closes):
        day = str(i + 1).zfill(2)
        ts = f"{base}{day}T00:00:00Z"
        bars.append(PriceBar(symbol=symbol, timestamp=ts, close=close))
    return bars


def _make_prices(n_days: int = 20) -> dict[str, list[PriceBar]]:
    """构造 3 个 symbol 各 n_days 天的价格序列。"""
    import math
    btc = [100.0 * (1 + 0.01 * math.sin(i)) for i in range(n_days)]
    eth = [50.0 * (1 + 0.015 * math.cos(i)) for i in range(n_days)]
    sol = [20.0 * (1 + 0.02 * math.sin(i + 1)) for i in range(n_days)]
    return {
        "BTC": _make_bars("BTC", btc),
        "ETH": _make_bars("ETH", eth),
        "SOL": _make_bars("SOL", sol),
    }


# ─── Task 1 测试：backtest_type 字段存在 ─────────────────────────────────────

def test_backtest_result_has_backtest_type_field(tmp_path: Path, monkeypatch) -> None:
    """BacktestResult 应有 backtest_type 字段，默认值为 'static'。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.05,
            max_drawdown=-0.03,
            sharpe=1.2,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        assert row.backtest_type == "static"


# ─── Task 2 测试：run_dynamic_backtest ───────────────────────────────────────

def test_run_dynamic_backtest_basic() -> None:
    """基本动态回测：3 个 symbol，20 天数据，每7天再平衡。"""
    prices = _make_prices(n_days=20)
    strategy = EqualWeightStrategy()

    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=7,
    )

    assert metrics.periods > 0
    assert isinstance(metrics.total_return, float)
    assert metrics.max_drawdown <= 0
    assert isinstance(metrics.sharpe, float)
    assert set(final_weights.keys()) == {"BTC", "ETH", "SOL"}
    assert abs(sum(final_weights.values()) - 1.0) < 1e-6


def test_warmup_fallback_equal_weight() -> None:
    """数据不足时（MomentumStrategy 需 30 天，只给 5 天），应降级为等权重，不抛出异常。"""
    prices = _make_prices(n_days=5)
    strategy = MomentumStrategy()  # 默认 lookback_days=30，数据不足

    # 不应抛出异常
    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=7,
    )

    assert metrics.periods > 0
    # 等权重：3 个 symbol 各 1/3
    for w in final_weights.values():
        assert abs(w - 1 / 3) < 1e-6


def test_no_lookahead_bias() -> None:
    """验证每次调用 compute_weights 时，prices 只包含 block_start 之前的数据。"""
    prices = _make_prices(n_days=20)
    seen_max_timestamps: list[str] = []

    class RecordingStrategy(BaseStrategy):
        params = {}

        def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
            if ctx.prices.empty:
                raise ValueError("no data")
            # 记录当前 context 中 DataFrame 的行数（代表历史数据量）
            seen_max_timestamps.append(str(len(ctx.prices)))
            n = len(ctx.prices.columns)
            return {sym: 1.0 / n for sym in ctx.prices.columns}

    strategy = RecordingStrategy()
    # 运行回测，rebalance_days=5，20 天共 4 块
    run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=5)

    # Block 0 (start=ts0): history = ts < ts0 → 0 行 → raises → fallback（不记录）
    # Block 1 (start=ts5): history = ts0..ts4 → 5 行 → 记录 "5"
    # Block 2 (start=ts10): history = ts0..ts9 → 10 行 → 记录 "10"
    # Block 3 (start=ts15): history = ts0..ts14 → 15 行 → 记录 "15"
    assert seen_max_timestamps == ["5", "10", "15"]


def test_run_dynamic_backtest_with_fee() -> None:
    """交易成本不为零时 total_return 应低于无成本版本。"""
    prices = _make_prices(n_days=20)
    strategy = EqualWeightStrategy()

    metrics_no_fee, _ = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7, fee_bps=0.0)
    metrics_with_fee, _ = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7, fee_bps=50.0)

    assert metrics_with_fee.total_return < metrics_no_fee.total_return
