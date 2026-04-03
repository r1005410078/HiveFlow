import math

from application.factor.basic_factor_service import compute_basic_factor_snapshot


def _snapshot_5symbols() -> dict:
    """Reusable L2 snapshot with 5 symbols × 6 factors = 30 rows."""
    return compute_basic_factor_snapshot(
        as_of="2026-04-01",
        symbols=["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"],
    )


def test_signal_matrix_structure():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    assert result["schema_version"] == "1.0"
    assert result["producer_version"] == "quant-l3"
    assert result["signal_version"] == "l3-signal-v1.0"
    assert isinstance(result["generated_at"], str)
    assert set(result["factor_names"]) == {
        "momentum_20", "inv_volatility_20", "turnover_rate",
        "max_drawdown_60", "trend_stability_20", "relative_strength_vs_index",
    }
    assert len(result["rows"]) == 30
    assert len(result["composite_scores"]) == 5
    assert len(result["transform_stats"]) == 6


def test_signal_row_fields():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)
    row = result["rows"][0]
    assert "symbol" in row
    assert "factor_name" in row
    assert "raw_value" in row
    assert "signal_value" in row
    assert "direction" in row
    assert isinstance(row["signal_value"], float)


def test_zscore_properties():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    for ts in result["transform_stats"]:
        post = ts["post_zscore"]
        if post["count"] > 2:
            assert abs(post["mean"]) < 0.01, f"{ts['factor_name']} post mean not ≈ 0"
            assert abs(post["std"] - 1.0) < 0.1, f"{ts['factor_name']} post std not ≈ 1"


def test_composite_equal_weight():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)

    rows_by_symbol: dict[str, list[float]] = {}
    for row in result["rows"]:
        if not math.isnan(row["signal_value"]):
            rows_by_symbol.setdefault(row["symbol"], []).append(row["signal_value"])

    for cs in result["composite_scores"]:
        if cs["factor_count"] > 0:
            expected = sum(rows_by_symbol[cs["symbol"]]) / len(rows_by_symbol[cs["symbol"]])
            assert abs(cs["composite_score"] - expected) < 1e-6, (
                f"{cs['symbol']}: expected {expected}, got {cs['composite_score']}"
            )


def test_empty_snapshot():
    from application.signal.signal_engineering_service import compute_signal_matrix

    empty = {"rows": [], "factor_names": [], "coverage_rate": 0.0}
    result = compute_signal_matrix(empty)
    assert result["rows"] == []
    assert result["composite_scores"] == []
    assert result["coverage_rate"] == 0.0
    assert result["transform_stats"] == []


def test_coverage_rate():
    from application.signal.signal_engineering_service import compute_signal_matrix

    snapshot = _snapshot_5symbols()
    result = compute_signal_matrix(snapshot)
    assert result["coverage_rate"] == 1.0


def test_direction_flip():
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"as_of": "2026-04-01", "symbol": f"SYM{i}", "factor_name": "test_factor",
         "factor_version": "v1", "raw_value": float(i), "direction": -1,
         "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i in range(1, 6)
    ]
    snapshot = {"rows": rows, "factor_names": ["test_factor"], "coverage_rate": 1.0}
    result = compute_signal_matrix(snapshot)

    signal_values = {r["symbol"]: r["signal_value"] for r in result["rows"]}
    assert signal_values["SYM1"] > signal_values["SYM5"], (
        "direction=-1 should flip: SYM1 (raw=1) should have higher signal than SYM5 (raw=5)"
    )


def test_single_value_factor_produces_nan():
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"as_of": "2026-04-01", "symbol": "SYM1", "factor_name": "solo",
         "factor_version": "v1", "raw_value": 5.0, "direction": 1,
         "unit": "ratio", "missing_strategy": "none", "source": "real"}
    ]
    snapshot = {"rows": rows, "factor_names": ["solo"], "coverage_rate": 1.0}
    result = compute_signal_matrix(snapshot)

    assert len(result["rows"]) == 1
    assert math.isnan(result["rows"][0]["signal_value"])
    assert result["transform_stats"][0]["post_zscore"]["count"] == 1
