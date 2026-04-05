import math

from application.factor.basic_factor_service import compute_basic_factor_snapshot


def _snapshot_5symbols() -> dict:
    """Reusable L2 snapshot with 5 symbols × 6 factors = 30 rows."""
    return compute_basic_factor_snapshot(
        as_of="2026-04-01",
        symbols=["000001.SZ", "600519.SH", "300750.SZ", "601318.SH", "000333.SZ"],
    )


def test_run_signal_snapshot_data_envelope():
    """HTTP/CLI：data 为 { signal_matrix, technical }，不再将矩阵放在 data 根上。"""
    from application.signal.signal_engineering_service import run_signal_snapshot

    out = run_signal_snapshot(as_of="2026-04-01", bar_store=None)
    assert out["status"] == "ok"
    data = out["data"]
    assert "signal_matrix" in data
    assert "technical" in data
    sm = data["signal_matrix"]
    assert sm["signal_version"] == "l3-signal-v1.0"
    assert len(sm["rows"]) == 30
    # 无 bar_store 时不计算 MA 块
    assert data["technical"] is None


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


def test_fill_missing_uses_cross_sectional_median():
    import pandas as pd
    from application.signal.signal_engineering_service import _fill_missing_cross_sectional

    wide = pd.DataFrame(
        {"factor_a": [1.0, 2.0, float("nan"), 4.0], "factor_b": [10.0, 20.0, 30.0, 40.0]},
        index=["A", "B", "C", "D"],
    )
    filled, counts = _fill_missing_cross_sectional(wide)

    # median of [1.0, 2.0, 4.0] = 2.0
    assert filled.loc["C", "factor_a"] == 2.0
    assert counts["factor_a"] == 1
    assert counts["factor_b"] == 0
    assert filled.loc["A", "factor_a"] == 1.0  # unchanged


def test_fill_missing_all_nan_column_stays_nan():
    import pandas as pd
    from application.signal.signal_engineering_service import _fill_missing_cross_sectional

    wide = pd.DataFrame(
        {"factor_a": [float("nan"), float("nan")]},
        index=["A", "B"],
    )
    filled, counts = _fill_missing_cross_sectional(wide)

    assert math.isnan(filled.loc["A", "factor_a"])
    assert math.isnan(filled.loc["B", "factor_a"])
    assert counts["factor_a"] == 2


def test_neutralize_skips_when_one_symbol_per_industry():
    import pandas as pd
    from application.signal.signal_engineering_service import _neutralize_industry

    industry_map = {"A": "tech", "B": "finance", "C": "energy"}
    wide = pd.DataFrame({"factor_a": [1.0, 2.0, 3.0]}, index=["A", "B", "C"])

    result = _neutralize_industry(wide, industry_map)

    # Every industry has exactly 1 symbol → guard fires → return original values
    pd.testing.assert_frame_equal(result, wide)


def test_neutralize_removes_industry_mean_with_multi_symbol():
    import pandas as pd
    from application.signal.signal_engineering_service import _neutralize_industry

    # A and B share "tech" industry; C is alone in "finance"
    industry_map = {"A": "tech", "B": "tech", "C": "finance"}
    wide = pd.DataFrame({"factor_a": [3.0, 1.0, 5.0]}, index=["A", "B", "C"])

    result = _neutralize_industry(wide, industry_map)

    # Within "tech": A=3, B=1, industry mean=2 → residuals A=+1, B=-1, sum=0
    residual_sum = result.loc["A", "factor_a"] + result.loc["B", "factor_a"]
    assert abs(residual_sum) < 1e-9, f"industry residuals must sum to 0, got {residual_sum}"


def test_compute_signal_matrix_fill_count_in_transform_stats():
    """transform_stats entries must include fill_count when a value is missing."""
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"symbol": sym, "factor_name": "f1", "factor_version": "v1",
         "raw_value": float("nan") if sym == "C" else float(i + 1),
         "direction": 1, "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i, sym in enumerate(["A", "B", "C", "D", "E"])
    ]
    snapshot = {"rows": rows, "factor_names": ["f1"], "coverage_rate": 0.8}
    result = compute_signal_matrix(snapshot)

    ts = result["transform_stats"][0]
    assert "fill_count" in ts, "fill_count must be present in transform_stats entry"
    assert ts["fill_count"] == 1, f"expected 1 fill, got {ts['fill_count']}"


def test_compute_signal_matrix_end_to_end_no_nan_composite():
    """When a factor value is missing, fill restores coverage so composite_score is not NaN."""
    import math
    from application.signal.signal_engineering_service import compute_signal_matrix

    rows = [
        {"symbol": sym, "factor_name": "f1", "factor_version": "v1",
         "raw_value": float("nan") if sym == "C" else float(i + 1),
         "direction": 1, "unit": "ratio", "missing_strategy": "none", "source": "real"}
        for i, sym in enumerate(["A", "B", "C", "D", "E"])
    ]
    snapshot = {"rows": rows, "factor_names": ["f1"], "coverage_rate": 0.8}
    result = compute_signal_matrix(snapshot)

    for cs in result["composite_scores"]:
        assert not math.isnan(cs["composite_score"]), (
            f"{cs['symbol']} composite_score is NaN after fill should have restored it"
        )
