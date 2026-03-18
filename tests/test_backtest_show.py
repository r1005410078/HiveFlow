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
