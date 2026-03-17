# tests/test_strategy_max_sharpe.py
import sys
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.max_sharpe import MaxSharpeStrategy


def _ctx(rows=90) -> StrategyContext:
    rng = np.random.default_rng(20)
    symbols = ("BTC", "ETH", "USDT")
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(50, 200, size=(rows, 3)),
        index=dates, columns=list(symbols),
    )
    prices["USDT"] = 1.0
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _ctx()
    weights = MaxSharpeStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _ctx()
    weights = MaxSharpeStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_no_crash_without_pypfopt(monkeypatch):
    import sys
    for key in list(sys.modules.keys()):
        if "pypfopt" in key:
            monkeypatch.delitem(sys.modules, key)
    monkeypatch.setitem(sys.modules, "pypfopt", None)
    ctx = _ctx()
    weights = MaxSharpeStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
