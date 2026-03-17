import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.bollinger_band import BollingerBandStrategy


def _oversold_prices(symbols=("BTC", "ETH", "USDT"), rows=40) -> StrategyContext:
    """BTC 当前价格远低于布林下轨（超卖），ETH 在中轨附近。"""
    rng = np.random.default_rng(3)
    dates = pd.date_range("2025-01-01", periods=rows)
    data = {}
    btc = rng.normal(100, 10, rows)
    btc[-1] = 60  # far below lower band
    data["BTC"] = btc
    eth = rng.normal(200, 5, rows)
    eth[-1] = 200  # at midband
    data["ETH"] = eth
    data["USDT"] = np.ones(rows)
    prices = pd.DataFrame(data, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_oversold_asset_gets_higher_weight():
    ctx = _oversold_prices()
    weights = BollingerBandStrategy().compute_weights(ctx)
    assert weights.get("BTC", 0) > weights.get("ETH", 0)
