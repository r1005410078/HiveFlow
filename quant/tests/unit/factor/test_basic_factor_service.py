from datetime import date, timedelta

from application.factor.basic_factor_service import (
    FACTOR_METADATA,
    compute_basic_factor_snapshot,
    compute_basic_factor_snapshot_from_bars,
)


def test_compute_basic_factor_snapshot_shape() -> None:
    out = compute_basic_factor_snapshot(
        as_of="2026-04-01",
        symbols=["000001.SZ", "600519.SH"],
    )

    assert out["snapshot_version"] == "l2-basic-v1.1"
    assert set(out["factor_names"]) == {
        "momentum_20",
        "inv_volatility_20",
        "turnover_rate",
        "max_drawdown_60",
        "trend_stability_20",
        "relative_strength_vs_index",
    }
    assert out["coverage_rate"] == 1.0
    assert len(out["rows"]) == 12
    assert out["rows"][0]["as_of"] == "2026-04-01"
    assert out["rows"][0]["factor_version"] in {m["version"] for m in FACTOR_METADATA.values()}


def _build_monotonic_bars(symbol: str, start: date, days: int, base_close: float) -> list[dict]:
    rows = []
    for i in range(days):
        d = start + timedelta(days=i)
        close = base_close + i
        rows.append(
            {
                "symbol": symbol,
                "timeframe": "1d",
                "bar_time": f"{d.isoformat()}T15:00:00+08:00",
                "open": close - 0.5,
                "high": close + 0.5,
                "low": close - 1.0,
                "close": close,
                "volume": 1000 + i,
                "amount": (1000 + i) * close,
                "adj_factor": 1.0,
                "data_source": "test",
            }
        )
    # Simulate DB query order (newest first).
    return list(reversed(rows))


def test_compute_basic_factor_snapshot_from_bars_prefers_real_data() -> None:
    bars = _build_monotonic_bars("600519.SH", start=date(2026, 1, 1), days=80, base_close=100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH", "000001.SZ"],
        bar_rows=bars,
    )

    assert out["snapshot_version"] == "l2-basic-v1.1"
    assert len(out["rows"]) == 12

    sh_rows = [r for r in out["rows"] if r["symbol"] == "600519.SH"]
    assert len(sh_rows) == 6

    trend = next(r for r in sh_rows if r["factor_name"] == "trend_stability_20")
    mdd = next(r for r in sh_rows if r["factor_name"] == "max_drawdown_60")
    rs = next(r for r in sh_rows if r["factor_name"] == "relative_strength_vs_index")
    assert trend["raw_value"] == 1.0
    assert mdd["raw_value"] == 1.0
    assert rs["raw_value"] > 1.0


def test_per_factor_version_in_deterministic_snapshot() -> None:
    out = compute_basic_factor_snapshot(as_of="2026-04-01", symbols=["000001.SZ"])
    versions = {r["factor_name"]: r["factor_version"] for r in out["rows"]}
    assert versions["momentum_20"] == "l2-momentum-v1.0"
    assert versions["inv_volatility_20"] == "l2-inv-vol-v1.0"
    assert versions["turnover_rate"] == "l2-turnover-v1.0"
    assert versions["max_drawdown_60"] == "l2-mdd-v1.0"
    assert versions["trend_stability_20"] == "l2-trend-stab-v1.0"
    assert versions["relative_strength_vs_index"] == "l2-rsi-v1.1"


def test_row_schema_contains_metadata_fields() -> None:
    out = compute_basic_factor_snapshot(as_of="2026-04-01", symbols=["600519.SH"])
    row = out["rows"][0]
    assert "direction" in row
    assert "unit" in row
    assert "missing_strategy" in row
    assert "source" in row
    assert row["direction"] == 1
    assert row["source"] == "deterministic_fallback"
    assert row["unit"] == "return"
    assert row["missing_strategy"] == "deterministic_fallback"


def test_bars_row_source_is_real_when_data_sufficient() -> None:
    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01", symbols=["600519.SH"], bar_rows=bars
    )
    for row in out["rows"]:
        if row["symbol"] == "600519.SH":
            if row["factor_name"] == "relative_strength_vs_index":
                assert row["source"] == "benchmark_proxy_fallback", "rs without benchmark should be proxy fallback"
            else:
                assert row["source"] == "real", f"{row['factor_name']} should be real"


def test_relative_strength_uses_real_benchmark_when_provided() -> None:
    symbol_bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    # 基准 base_close=200，绝对增幅相同（+1/day），但比例更小；个股涨幅相对更高
    benchmark_bars = _build_monotonic_bars("000300.SH", date(2026, 1, 1), 80, 200.0)

    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=symbol_bars,
        benchmark_rows=benchmark_bars,
    )
    rs_row = next(r for r in out["rows"] if r["factor_name"] == "relative_strength_vs_index")
    assert rs_row["source"] == "real"
    # 个股涨幅 > 基准涨幅（relative），相对强度应 > 0
    assert rs_row["raw_value"] > 0.0


def test_stability_metrics_present_in_snapshot() -> None:
    from datetime import date

    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01", symbols=["600519.SH"], bar_rows=bars
    )
    assert "stability_metrics" in out
    metrics = out["stability_metrics"]
    assert isinstance(metrics, list)
    assert len(metrics) == 6  # one per factor
    m = metrics[0]
    assert "factor_name" in m
    assert "factor_version" in m
    assert "coverage_rate" in m
    assert "real_count" in m
    assert "fallback_count" in m
    assert "mean_value" in m
    assert "std_value" in m
    assert m["drift_flag"] is None   # no historical_baselines provided
    assert m["drift_z_score"] is None
    # With sufficient bars, real_count > 0, so coverage_rate > 0
    assert m["coverage_rate"] > 0.0


def test_stability_metrics_drift_flag_when_baselines_provided() -> None:
    from datetime import date

    bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    # Set momentum_20 baseline mean to extreme value to trigger drift
    baselines = {
        "momentum_20": {"mean": 0.0, "std": 0.001},  # actual value will be >> 2σ away
    }
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=bars,
        historical_baselines=baselines,
    )
    m_momentum = next(m for m in out["stability_metrics"] if m["factor_name"] == "momentum_20")
    assert m_momentum["drift_flag"] is True
    assert m_momentum["drift_z_score"] is not None
    # Other factors without baselines should have drift_flag = None
    m_inv_vol = next(m for m in out["stability_metrics"] if m["factor_name"] == "inv_volatility_20")
    assert m_inv_vol["drift_flag"] is None


def test_relative_strength_falls_back_to_proxy_without_benchmark() -> None:
    symbol_bars = _build_monotonic_bars("600519.SH", date(2026, 1, 1), 80, 100.0)
    out = compute_basic_factor_snapshot_from_bars(
        as_of="2026-04-01",
        symbols=["600519.SH"],
        bar_rows=symbol_bars,
        benchmark_rows=None,
    )
    rs_row = next(r for r in out["rows"] if r["factor_name"] == "relative_strength_vs_index")
    assert rs_row["source"] == "benchmark_proxy_fallback"
    # 其他因子仍为 real
    other_rows = [r for r in out["rows"] if r["factor_name"] != "relative_strength_vs_index"]
    assert all(r["source"] == "real" for r in other_rows)
