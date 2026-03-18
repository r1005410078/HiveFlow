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
