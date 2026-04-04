from __future__ import annotations


def _make_bar_store_with_25_bars():
    """Bar store with 25 bars per symbol — enough for covariance."""
    symbols = ["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"]
    rows = []
    for i, sym in enumerate(symbols):
        for d in range(25):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00",
                "close": 100.0 + i * 5 + d * 0.3,
            })

    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

        def list_storage_bars(
            self,
            symbols=None,
            storage_timeframe="1m",
            start_date=None,
            end_date=None,
            limit=None,
            order="asc",
        ):
            del storage_timeframe, start_date, end_date, limit, order
            syms = symbols or []
            return [r for r in rows if r["symbol"] in syms]

        def list_symbols_with_min_bars_in_window(self, **kwargs):
            return ([], False)

    return _MockBarStore()


def test_run_portfolio_optimize_returns_valid_schema():
    """Output must conform to CLI envelope and target_weights must sum to 1."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    bar_store = _make_bar_store_with_25_bars()
    alpha = {
        "000001.SZ": 0.5,
        "600519.SH": 1.2,
        "300750.SZ": 0.9,
        "601318.SH": 0.7,
        "000333.SZ": 0.3,
    }
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=alpha, bar_store=bar_store)

    assert result["schema_version"] == "1.0.0"
    assert result["command"] == "hf portfolio optimize"
    assert result["source"] == "system"
    assert result["advice_only"] is False
    assert result["decision_weight"] == 1
    assert "data" in result

    data = result["data"]
    assert data["as_of"] == "2026-02-01"
    assert data["optimization_status"] in (
        "optimal", "optimal_inaccurate", "fallback_equal_weight", "fallback_prev_weight"
    )
    weights = [row["weight"] for row in data["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4


def test_fallback_produces_warning_status():
    """When solver fallback occurs, CLI envelope status must be 'warning'."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    # w_max=0.05 makes problem infeasible for 5 symbols  (5 * 0.05 = 0.25 < 1)
    alpha = {
        "000001.SZ": 1.0, "600519.SH": 1.0, "300750.SZ": 1.0,
        "601318.SH": 1.0, "000333.SZ": 1.0,
    }
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=alpha, w_max=0.05)

    assert result["status"] == "warning"
    assert result["data"]["optimization_status"] == "fallback_equal_weight"
    assert any(w["code"] == "PORTFOLIO_OPTIMIZATION_FALLBACK" for w in result["warnings"])


def test_alpha_defaults_from_l3_when_not_provided():
    """When alpha is None, service must derive it from L3 signal snapshot."""
    from application.portfolio.portfolio_optimize_service import run_portfolio_optimize

    # Without bar_store, signal snapshot uses deterministic factor snapshot
    result = run_portfolio_optimize(as_of="2026-02-01", alpha=None)

    data = result["data"]
    assert len(data["target_weights"]) > 0
    weights = [row["weight"] for row in data["target_weights"]]
    assert abs(sum(weights) - 1.0) < 1e-4
