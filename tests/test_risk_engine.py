"""风险引擎纯计算测试。"""
from __future__ import annotations

import math

from hiveflow.services.backtest_engine import PriceBar
from hiveflow.services.risk_engine import (
    AssetVolatility,
    CorrelationMatrix,
    AssetDrawdown,
    compute_volatility,
    compute_correlation,
    compute_drawdown,
    compute_portfolio_risk,
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


def test_compute_drawdown_basic() -> None:
    """100 → 200 → 100：MDD = -0.5。"""
    prices = {"BTC": _make_bars("BTC", [100.0, 200.0, 100.0])}
    results = compute_drawdown(prices)
    assert len(results) == 1
    assert abs(results[0].max_drawdown - (-0.5)) < 1e-9
    assert results[0].periods == 3


def test_compute_drawdown_flat() -> None:
    """平坦价格序列 → MDD == 0.0。"""
    prices = {"USDT": _make_bars("USDT", [1.0, 1.0, 1.0, 1.0])}
    results = compute_drawdown(prices)
    assert results[0].max_drawdown == 0.0


def test_compute_drawdown_sorts_ascending() -> None:
    """结果按 max_drawdown 升序（最大亏损在前）。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0, 200.0, 50.0]),
        "ETH": _make_bars("ETH", [100.0, 110.0, 100.0]),
    }
    results = compute_drawdown(prices)
    assert results[0].max_drawdown <= results[1].max_drawdown


def test_compute_portfolio_risk_basic() -> None:
    """curve = [1.0, 1.1, 1.05, 1.2]: win_rate = 2/3, calmar > 0。"""
    curve = [1.0, 1.1, 1.05, 1.2]
    result = compute_portfolio_risk(curve)
    assert "annual_vol" in result
    assert "win_rate" in result
    assert "calmar_ratio" in result
    assert abs(result["win_rate"] - 2 / 3) < 1e-9
    assert result["calmar_ratio"] > 0


def test_compute_portfolio_risk_too_short() -> None:
    """len(curve) < 2 应抛 ValueError。"""
    import pytest
    with pytest.raises(ValueError):
        compute_portfolio_risk([1.0])


def test_compute_volatility_with_cn_annualization() -> None:
    """传 annualization_factor=252 时，annual_vol == daily_vol × sqrt(252)。"""
    prices = {"000001.SZ": _make_bars("000001.SZ", [10.0, 10.5, 10.3, 10.8, 10.6])}
    results = compute_volatility(prices, annualization_factor=252)
    assert len(results) == 1
    v = results[0]
    assert abs(v.annual_vol - v.daily_vol * math.sqrt(252)) < 1e-9


def test_compute_volatility_default_is_365() -> None:
    """不传 annualization_factor 时默认 365（向后兼容）。"""
    prices = {"BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0, 110.0])}
    default_results = compute_volatility(prices)
    explicit_results = compute_volatility(prices, annualization_factor=365)
    assert abs(default_results[0].annual_vol - explicit_results[0].annual_vol) < 1e-12


def test_compute_portfolio_risk_with_cn_annualization() -> None:
    """传 annualization_factor=252 时，annual_vol 使用 252 年化。"""
    curve = [100.0, 102.0, 101.5, 103.0, 102.5, 104.0]
    result_365 = compute_portfolio_risk(curve, annualization_factor=365)
    result_252 = compute_portfolio_risk(curve, annualization_factor=252)
    # 252 年化的 annual_vol 应比 365 小
    assert result_252["annual_vol"] < result_365["annual_vol"]
    # 比例接近 sqrt(252/365)
    ratio = result_252["annual_vol"] / result_365["annual_vol"]
    assert abs(ratio - math.sqrt(252 / 365)) < 1e-9
