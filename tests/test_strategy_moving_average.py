import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.moving_average import MovingAverageCrossStrategy


def _trend_prices(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    """BTC 金叉（短期均线 > 长期均线），ETH 死叉。"""
    dates = pd.date_range("2025-01-01", periods=rows)
    data = {}
    data["BTC"] = np.linspace(100, 200, rows)  # rising
    data["ETH"] = np.linspace(200, 100, rows)  # falling
    data["USDT"] = np.ones(rows)
    prices = pd.DataFrame(data, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_golden_cross_gets_higher_weight():
    ctx = _trend_prices()
    weights = MovingAverageCrossStrategy().compute_weights(ctx)
    assert weights.get("BTC", 0) > weights.get("ETH", 0)
