"""量化策略应用层集成测试。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.application.quant_strategies import (
    run_quant_strategy,
    list_strategy_runs,
    QuantRunResult,
)
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


class _MockStrategy(BaseStrategy):
    params: dict = {"min_usdt": 0.10}

    def compute_weights(self, ctx: StrategyContext) -> dict[str, float]:
        return {"BTC": 0.60, "ETH": 0.30, "USDT": 0.10}


def _make_settings(tmp_path):
    db = tmp_path / "test.db"
    return Settings(database_url=f"sqlite:///{db}")


def _seed_market_bars(settings, symbols=("BTC", "ETH", "USDT"), rows=60):
    from hiveflow.domain.market_data import MarketBar

    rng = np.random.default_rng(99)
    base_date = datetime(2025, 1, 1)

    with get_session(settings) as session:
        for i in range(rows):
            ts = base_date + timedelta(days=i)
            for sym in symbols:
                bar = MarketBar(
                    symbol=sym,
                    timestamp=ts,
                    open=float(rng.uniform(90, 110)),
                    high=float(rng.uniform(110, 120)),
                    low=float(rng.uniform(80, 90)),
                    close=float(rng.uniform(90, 110)),
                    volume=1000.0,
                )
                session.add(bar)
        session.commit()


def test_run_quant_strategy_saves_to_db(tmp_path):
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    result = run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        settings=settings,
    )

    assert isinstance(result, QuantRunResult)
    assert result.run_id is not None
    assert result.strategy_name == "_MockStrategy"
    assert abs(sum(result.weights.values()) - 1.0) < 1e-9
    assert result.applied is False


def test_run_quant_strategy_with_apply(tmp_path):
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    result = run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        apply=True,
        settings=settings,
    )

    assert result.applied is True

    from hiveflow.domain.allocations import TargetAllocation
    from sqlmodel import select
    with get_session(settings) as session:
        rows = session.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "_MockStrategy"
        )).all()
    assert len(rows) > 0
    symbols = {r.symbol for r in rows}
    assert "BTC" in symbols


def test_run_quant_strategy_apply_writes_decision_log(tmp_path):
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        apply=True,
        settings=settings,
    )

    from hiveflow.domain.decision_logs import DecisionLog
    from sqlmodel import select
    with get_session(settings) as session:
        logs = session.exec(select(DecisionLog).where(
            DecisionLog.decision_type == "quant-run-apply"
        )).all()
    assert len(logs) > 0
    assert "_MockStrategy" in logs[0].summary   # DecisionLog uses 'summary', not 'content'


def test_list_strategy_runs(tmp_path):
    settings = _make_settings(tmp_path)
    create_all_tables(settings)
    _seed_market_bars(settings)

    run_quant_strategy(
        strategy_class=_MockStrategy,
        strategy_file=None,
        params={},
        settings=settings,
    )

    runs = list_strategy_runs(limit=10, settings=settings)
    assert len(runs) == 1
    assert runs[0].strategy_name == "_MockStrategy"
