from datetime import date, timedelta

from application.factor_optimization.analysis_service import analyze_factors


def _bars_for_symbol(symbol: str, n: int, close0: float, vol0: float) -> list[dict]:
    base = date(2026, 1, 1)
    rows = []
    for i in range(n):
        d = base + timedelta(days=i)
        rows.append(
            {
                "symbol": symbol,
                "bar_time": f"{d.isoformat()}T15:00:00+08:00",
                "close": close0 + i * 0.02,
                "volume": vol0 + i * 10,
            }
        )
    return rows


def test_analyze_factors_insufficient_bars_returns_zero_health() -> None:
    bars = [
        {"symbol": "000001.SZ", "bar_time": "2026-03-01T15:00:00+08:00", "close": 10.0, "volume": 1000},
        {"symbol": "000001.SZ", "bar_time": "2026-03-02T15:00:00+08:00", "close": 10.3, "volume": 1100},
        {"symbol": "600519.SH", "bar_time": "2026-03-01T15:00:00+08:00", "close": 1500.0, "volume": 2200},
        {"symbol": "600519.SH", "bar_time": "2026-03-02T15:00:00+08:00", "close": 1512.0, "volume": 2300},
    ]

    out = analyze_factors(
        bars=bars,
        factor_names=["momentum_20", "inv_volatility_20", "turnover_rate"],
        forward_days=1,
    )

    assert {"factor_health", "correlation_matrix", "coverage"} <= set(out.keys())
    assert len(out["factor_health"]) == 3
    assert all(x["ic"] == 0.0 for x in out["factor_health"])


def test_analyze_factors_pit_produces_health_with_sufficient_history() -> None:
    bars = _bars_for_symbol("000001.SZ", 70, 10.0, 1000) + _bars_for_symbol("600519.SH", 70, 100.0, 2000)
    out = analyze_factors(
        bars=bars,
        factor_names=["momentum_20", "inv_volatility_20", "turnover_rate"],
        forward_days=1,
    )
    assert out["coverage"]["bars"] == 140
    assert len(out["factor_health"]) == 3
    for row in out["factor_health"]:
        assert "ic" in row and "sharpe" in row and "max_drawdown" in row
    m20 = out["correlation_matrix"]["momentum_20"]["momentum_20"]
    assert abs(m20 - 1.0) < 1e-5
