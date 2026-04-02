from application.factor_optimization.analysis_service import analyze_factors


def test_analyze_factors_returns_ic_sharpe_drawdown_and_correlation() -> None:
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
    assert all("ic" in x and "sharpe" in x and "max_drawdown" in x for x in out["factor_health"])
