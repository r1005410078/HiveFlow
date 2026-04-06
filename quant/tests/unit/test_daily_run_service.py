def test_run_daily_passes_benchmark_rows_to_factor_service(monkeypatch) -> None:
    """Verify benchmark bars are queried and passed when bar_store is available."""
    from application.daily_run_service import run_daily
    import application.factor.basic_factor_service as svc
    import application.daily_run_service as daily_svc

    captured = {}

    class FakeBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return []

        def list_storage_bars(
            self,
            symbols=None,
            storage_timeframe="1m",
            start_date=None,
            end_date=None,
            limit=None,
            order="asc",
        ):
            del symbols, storage_timeframe, start_date, end_date, limit, order
            return []

        def list_symbols_with_min_bars_in_window(self, **kwargs):
            return ([], False)

    original = svc.compute_basic_factor_snapshot_from_bars

    def patched(as_of, symbols, bar_rows, benchmark_rows=None, historical_baselines=None):
        captured["benchmark_rows"] = benchmark_rows
        return original(as_of=as_of, symbols=symbols, bar_rows=bar_rows,
                        benchmark_rows=benchmark_rows, historical_baselines=historical_baselines)

    monkeypatch.setattr(daily_svc, "compute_basic_factor_snapshot_from_bars", patched)

    run_daily(as_of="2026-04-01", root=None, bar_store=FakeBarStore())
    assert captured.get("benchmark_rows") == []


def test_daily_run_includes_risk_gate():
    """daily run output must include data.risk_gate when portfolio succeeds."""
    from application.daily_run_service import run_daily

    result = run_daily(as_of="2026-04-01", root=None, bar_store=None)
    data = result["data"]
    # risk_gate may be None only if portfolio is None; if portfolio exists, risk_gate must be a dict
    if data.get("portfolio") is not None:
        assert data.get("risk_gate") is not None
        assert "risk_gate" in data["risk_gate"]  # "pass" or "block"
        assert "regime" in data["risk_gate"]
        assert "checks" in data["risk_gate"]


def test_daily_run_includes_pretrade_when_portfolio_ok():
    """When portfolio is present, L5.5 pretrade payload must be attached."""
    from application.daily_run_service import run_daily

    result = run_daily(as_of="2026-04-01", root=None, bar_store=None)
    data = result["data"]
    if data.get("portfolio") is not None:
        pt = data.get("pretrade")
        assert pt is not None
        assert "overall_tradable" in pt
        assert "orders" in pt
        assert "total_impact_bp" in pt
