# tests/test_strategy_risk_parity.py
import pandas as pd
import numpy as np
from hiveflow.services.strategies.base import StrategyContext
from hiveflow.services.strategies.risk_parity import RiskParityStrategy


def _vol_prices(symbols=("BTC", "ETH", "SOL", "USDT"), rows=60) -> StrategyContext:
    rng = np.random.default_rng(10)
    dates = pd.date_range("2025-01-01", periods=rows)
    btc = rng.normal(0, 3, rows).cumsum() + 100
    eth = rng.normal(0, 1.5, rows).cumsum() + 100
    sol = rng.normal(0, 0.5, rows).cumsum() + 100
    usdt = np.ones(rows)
    prices = pd.DataFrame({"BTC": btc, "ETH": eth, "SOL": sol, "USDT": usdt}, index=dates)
    return StrategyContext(prices=prices, current_positions={}, risk_signals={}, params={})


def test_weights_sum_to_one():
    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9


def test_min_usdt_respected():
    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert weights.get("USDT", 0) >= 0.10


def test_no_crash_without_pypfopt(monkeypatch):
    """PyPortfolioOpt 不可用时不崩溃，降级为等权重。"""
    import sys
    # Temporarily hide pypfopt
    pypfopt_modules = {k: v for k, v in sys.modules.items() if "pypfopt" in k}
    for k in pypfopt_modules:
        monkeypatch.delitem(sys.modules, k)
    monkeypatch.setitem(sys.modules, "pypfopt", None)

    ctx = _vol_prices()
    weights = RiskParityStrategy().compute_weights(ctx)
    assert abs(sum(weights.values()) - 1.0) < 1e-9
