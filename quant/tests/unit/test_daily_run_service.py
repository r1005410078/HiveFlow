def test_run_daily_passes_benchmark_rows_to_factor_service(monkeypatch) -> None:
    """Verify benchmark bars are queried and passed when bar_store is available."""
    from application.daily_run_service import run_daily
    import application.factor.basic_factor_service as svc
    import application.daily_run_service as daily_svc

    captured = {}

    class FakeBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return []

    original = svc.compute_basic_factor_snapshot_from_bars

    def patched(as_of, symbols, bar_rows, benchmark_rows=None, historical_baselines=None):
        captured["benchmark_rows"] = benchmark_rows
        return original(as_of=as_of, symbols=symbols, bar_rows=bar_rows,
                        benchmark_rows=benchmark_rows, historical_baselines=historical_baselines)

    monkeypatch.setattr(daily_svc, "compute_basic_factor_snapshot_from_bars", patched)

    run_daily(as_of="2026-04-01", root=None, bar_store=FakeBarStore())
    assert captured.get("benchmark_rows") == []
