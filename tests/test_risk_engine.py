"""风险引擎纯计算测试。"""
from __future__ import annotations

import math

from hiveflow.services.backtest_engine import PriceBar
from hiveflow.services.risk_engine import (
    AssetVolatility,
    compute_volatility,
)


def _make_bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, timestamp=f"2026-01-{i+1:02d}T00:00:00Z", close=c)
        for i, c in enumerate(closes)
    ]


def test_compute_volatility_basic() -> None:
    """annual_vol == daily_vol × sqrt(365)，且 annual_vol > daily_vol。"""
    prices = {"BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0, 110.0])}
    results = compute_volatility(prices)
    assert len(results) == 1
    v = results[0]
    assert v.symbol == "BTC"
    assert v.periods == 5
    assert v.daily_vol >= 0.0
    assert abs(v.annual_vol - v.daily_vol * math.sqrt(365)) < 1e-9


def test_compute_volatility_sorts_descending() -> None:
    """结果按 annual_vol 降序排列。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0]),
        "USDT": _make_bars("USDT", [1.0, 1.0, 1.0, 1.0]),
    }
    results = compute_volatility(prices)
    assert len(results) >= 1
    for i in range(len(results) - 1):
        assert results[i].annual_vol >= results[i + 1].annual_vol


def test_compute_volatility_insufficient_data() -> None:
    """少于 2 个价格点的资产应被跳过（不报错）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0]),
        "ETH": _make_bars("ETH", [50.0, 55.0, 52.0]),
    }
    results = compute_volatility(prices)
    symbols = [v.symbol for v in results]
    assert "BTC" not in symbols
    assert "ETH" in symbols
