import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.momentum import MomentumStrategy


def _rising_prices(symbols=("BTC", "ETH", "SOL", "USDT"), rows=60) -> StrategyContext:
    """BTC 涨最多，ETH 次之，SOL 持平，USDT 稳定。"""
    rng = np.random.default_rng(1)
    dates = pd.date_range("2025-01-01", periods=rows)
    base = rng.uniform(100, 200, size=(rows, len(symbols)))
    multiplier = np.linspace(1, 2, rows)
    base[:, 0] *= multiplier
    base[:, 1] *= np.linspace(1, 1.3, rows)
    base[:, 3] = 1.0
    prices = pd.DataFrame(base, index=dates, columns=list(symbols))
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_top_k_assets_selected():
    ctx = _rising_prices()
    ctx.params = {"top_k": 2, "lookback_days": 30, "min_usdt": 0.10}
    weights = MomentumStrategy().compute_weights(ctx)
    non_usdt_positive = [s for s, w in weights.items() if s != "USDT" and w > 1e-9]
    assert len(non_usdt_positive) == 2


def test_btc_has_highest_weight_in_rising_market():
    ctx = _rising_prices()
    weights = MomentumStrategy().compute_weights(ctx)
    non_usdt = {s: w for s, w in weights.items() if s != "USDT"}
    top_symbol = max(non_usdt, key=lambda s: non_usdt[s])
    assert top_symbol == "BTC"
