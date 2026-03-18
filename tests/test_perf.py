# tests/test_perf.py
"""Perf 追踪测试。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.portfolio_snapshots import PortfolioSnapshot


def _settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db")


def test_portfolio_snapshot_create_and_read(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    snap = PortfolioSnapshot(
        total_value_usd=10000.0,
        positions_json=json.dumps({"BTC": 0.6, "ETH": 0.4}),
        source="manual",
    )
    with get_session(settings) as session:
        session.add(snap)
        session.commit()
        session.refresh(snap)
        assert snap.id is not None
        assert snap.total_value_usd == 10000.0
        assert snap.source == "manual"
        assert snap.timestamp is not None


from hiveflow.application.perf import (
    list_snapshots,
    compare_with_backtest,
    PerfCompareResult,
    PortfolioSnapshotView,
    record_snapshot,
)
from hiveflow.domain.backtests import BacktestResult


def _seed_backtest_with_curve(session, curve: list[float]) -> BacktestResult:
    bt = BacktestResult(
        strategy_name="MomentumStrategy",
        prices_file="test.csv",
        periods=len(curve) - 1,
        total_return=curve[-1] / curve[0] - 1.0,
        max_drawdown=-0.1,
        sharpe=1.5,
        equity_curve=json.dumps(curve),
    )
    session.add(bt)
    session.commit()
    session.refresh(bt)
    session.expunge(bt)  # detach so bt.id remains accessible after session closes
    return bt


def _seed_snapshots(session, values: list[float], base_dt: datetime | None = None) -> None:
    if base_dt is None:
        base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, v in enumerate(values):
        snap = PortfolioSnapshot(
            timestamp=base_dt + timedelta(days=i),
            total_value_usd=v,
            positions_json=json.dumps({}),
            source="manual",
        )
        session.add(snap)
    session.commit()


def test_record_snapshot(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    positions_data = {"BTC": {"qty": 0.5, "value_usd": 5000.0}}
    view = record_snapshot(
        total_value_usd=10000.0,
        positions_data=positions_data,
        source="manual",
        settings=settings,
    )
    assert view.total_value_usd == 10000.0
    assert view.source == "manual"
    assert view.id is not None


def test_list_snapshots(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)
    with get_session(settings) as session:
        _seed_snapshots(session, [10000.0, 10200.0, 10500.0])

    views = list_snapshots(settings=settings)
    assert len(views) == 3
    # 最新在前
    assert views[0].total_value_usd == 10500.0


def test_compare_with_backtest_metrics(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    backtest_curve = [1.0, 1.05, 1.10, 1.08, 1.15]
    live_values = [10000.0, 10300.0, 10600.0, 10500.0, 10800.0]
    base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with get_session(settings) as session:
        bt = _seed_backtest_with_curve(session, backtest_curve)
        _seed_snapshots(session, live_values, base_dt)

    result = compare_with_backtest(backtest_id=bt.id, settings=settings)

    # 总收益率
    expected_live_return = 10800.0 / 10000.0 - 1.0  # 0.08
    assert abs(result.live_total_return - expected_live_return) < 1e-9
    assert abs(result.backtest_total_return - (1.15 / 1.0 - 1.0)) < 1e-9

    # 年化收益率：快照 5 条，跨度 Jan 1 → Jan 5（4 天），公式 (1+r)^(365/days)-1
    days = 4  # timedelta between Jan 1 and Jan 5 = 4 days
    expected_annual = (1 + expected_live_return) ** (365 / days) - 1
    assert result.live_annual_return is not None
    assert abs(result.live_annual_return - expected_annual) < 1e-6

    # MDD 为非正
    assert result.live_mdd <= 0.0
    assert result.backtest_mdd <= 0.0
    # Sparkline 存在
    assert len(result.live_sparkline) > 0
    assert len(result.backtest_sparkline) > 0


def test_compare_insufficient_snapshots_returns_na(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    backtest_curve = [1.0, 1.05]
    with get_session(settings) as session:
        bt = _seed_backtest_with_curve(session, backtest_curve)
        # 只有 1 条快照
        _seed_snapshots(session, [10000.0])

    result = compare_with_backtest(backtest_id=bt.id, settings=settings)

    assert result.live_annual_return is None  # N/A
    assert result.live_total_return is not None  # 仍有总收益率（单条时为 0）


def test_compare_nonexistent_backtest_raises(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)
    with pytest.raises(ValueError, match="不存在"):
        compare_with_backtest(backtest_id=9999, settings=settings)
