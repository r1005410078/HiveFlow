import pandas as pd
import numpy as np
import pytest
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


def _make_ctx(symbols=("BTC", "ETH", "USDT"), rows=60) -> StrategyContext:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2025-01-01", periods=rows)
    prices = pd.DataFrame(
        rng.uniform(100, 200, size=(rows, len(symbols))),
        index=dates,
        columns=list(symbols),
    )
    return StrategyContext(
        prices=prices,
        current_positions={"BTC": 0.5, "ETH": 0.4, "USDT": 0.1},
        risk_signals={},
        params={},
    )


def test_strategy_context_creation():
    ctx = _make_ctx()
    assert ctx.prices.shape == (60, 3)
    assert ctx.current_positions["BTC"] == 0.5
    assert ctx.risk_signals == {}


def test_base_strategy_raises_not_implemented():
    strategy = BaseStrategy()
    ctx = _make_ctx()
    with pytest.raises(NotImplementedError):
        strategy.compute_weights(ctx)
