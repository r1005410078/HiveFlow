"""回测权益曲线可视化测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.backtests import BacktestResult


def _seed_record(tmp_path: Path, monkeypatch, equity_curve=None) -> int:
    """在临时 DB 中种入一条 BacktestResult，返回其 id。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.12,
            max_drawdown=-0.05,
            sharpe=1.5,
            equity_curve=json.dumps(equity_curve) if equity_curve is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def test_backtest_result_has_equity_curve_field(tmp_path: Path, monkeypatch) -> None:
    """BacktestResult 应有 equity_curve 字段，默认为 None。"""
    rid = _seed_record(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    with get_session() as session:
        row = session.get(BacktestResult, rid)
        assert hasattr(row, "equity_curve")
        assert row.equity_curve is None


from hiveflow.services.backtest_engine import (
    BacktestMetrics,
    PriceBar,
    run_dynamic_backtest,
    run_weighted_backtest,
)
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy


def _make_bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, timestamp=f"2026-01-{i+1:02d}T00:00:00Z", close=c)
        for i, c in enumerate(closes)
    ]


def test_backtest_metrics_has_curve() -> None:
    """BacktestMetrics.curve 应存在，长度 == periods + 1，首值为 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(10)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(10)]),
    }
    weights = {"BTC": 0.6, "ETH": 0.4}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert hasattr(m, "curve")
    assert len(m.curve) == m.periods + 1
    assert m.curve[0] == 1.0


def test_run_weighted_backtest_curve() -> None:
    """上涨序列下 curve[-1] > 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 * (1 + 0.01 * i) for i in range(20)]),
        "ETH": _make_bars("ETH", [50.0 * (1 + 0.01 * i) for i in range(20)]),
    }
    weights = {"BTC": 0.5, "ETH": 0.5}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert m.curve[-1] > 1.0


def test_run_dynamic_backtest_curve() -> None:
    """动态回测 curve 长度 > 0，首值 == 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(30)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(30)]),
    }
    strategy = EqualWeightStrategy()
    (m, _) = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7)
    assert len(m.curve) > 0
    assert m.curve[0] == 1.0
