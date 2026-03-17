import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy


def _make_ctx(symbols=("BTC", "ETH", "SOL", "USDT"), rows=30) -> StrategyContext:
    rng = np.random.default_rng(0)
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(10, 200, size=(rows, len(symbols))),
        index=dates, columns=list(symbols),
    )
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _make_ctx()
    weights = EqualWeightStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _make_ctx()
    weights = EqualWeightStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_equal_distribution():
    """所有资产权重相等。"""
    ctx = _make_ctx(symbols=("BTC", "ETH", "USDT"))
    weights = EqualWeightStrategy().compute_weights(ctx)
    vals = list(weights.values())
    assert max(vals) - min(vals) < 1e-9


def test_custom_min_usdt():
    ctx = _make_ctx(symbols=("BTC", "ETH", "USDT"))
    ctx.params = {"min_usdt": 0.20}
    weights = EqualWeightStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.20
