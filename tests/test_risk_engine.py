"""风险引擎纯计算测试。"""
from __future__ import annotations

import math

from hiveflow.services.backtest_engine import PriceBar
from hiveflow.services.risk_engine import (
    AssetVolatility,
    CorrelationMatrix,
    compute_volatility,
    compute_correlation,
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


def test_compute_correlation_identity() -> None:
    """matrix[i][i] == 1.0（自相关为 1）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0]),
        "ETH": _make_bars("ETH", [50.0, 55.0, 52.0, 57.0]),
    }
    result = compute_correlation(prices)
    assert result.symbols == ["BTC", "ETH"]
    assert result.matrix[0][0] == 1.0
    assert result.matrix[1][1] == 1.0


def test_compute_correlation_perfect_positive() -> None:
    """完全相同的收益率序列 → 相关系数 == 1.0。"""
    closes = [100.0, 110.0, 121.0, 133.1]
    prices = {
        "A": _make_bars("A", closes),
        "B": _make_bars("B", [c * 0.5 for c in closes]),
    }
    result = compute_correlation(prices)
    i = result.symbols.index("A")
    j = result.symbols.index("B")
    assert abs(result.matrix[i][j] - 1.0) < 1e-9


def test_compute_correlation_aligns_timestamps() -> None:
    """两资产时间戳错开时，共同收益率点不足 2 → 对应位置为 nan。"""
    a_bars = [
        PriceBar(symbol="A", timestamp=f"2026-01-0{i+1}T00:00:00Z", close=c)
        for i, c in enumerate([100.0, 110.0, 120.0, 130.0])
    ]
    b_bars = [
        PriceBar(symbol="B", timestamp=f"2026-01-0{i+3}T00:00:00Z", close=c)
        for i, c in enumerate([50.0, 55.0, 60.0, 65.0])
    ]
    result = compute_correlation({"A": a_bars, "B": b_bars})
    i = result.symbols.index("A")
    j = result.symbols.index("B")
    assert math.isnan(result.matrix[i][j])
