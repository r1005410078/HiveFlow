import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.mean_reversion import MeanReversionStrategy


def _dip_prices(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    """BTC 当前价格比均值低很多（z-score 负），应获得最高权重。"""
    rng = np.random.default_rng(2)
    dates = pd.date_range("2025-01-01", periods=rows)
    data = rng.uniform(100, 200, size=(rows, len(symbols)))
    data[:, 0] = 150
    data[-1, 0] = 50   # BTC far below mean
    data[:, 1] = 150
    data[-1, 1] = 140  # ETH slightly below
    data[:, 2] = 1.0
    prices = pd.DataFrame(data, index=dates, columns=list(symbols))
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_dip_asset_gets_higher_weight():
    ctx = _dip_prices()
    weights = MeanReversionStrategy().compute_weights(ctx)
    assert weights["BTC"] > weights["ETH"]
