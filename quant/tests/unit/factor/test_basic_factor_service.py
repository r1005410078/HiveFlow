from application.factor.basic_factor_service import compute_basic_factor_snapshot


def test_compute_basic_factor_snapshot_shape() -> None:
    out = compute_basic_factor_snapshot(
        as_of="2026-04-01",
        symbols=["000001.SZ", "600519.SH"],
    )

    assert out["factor_version"] == "l2-basic-v1"
    assert set(out["factor_names"]) == {"momentum_20", "inv_volatility_20", "turnover_rate"}
    assert out["coverage_rate"] == 1.0
    assert len(out["rows"]) == 6
    assert out["rows"][0]["as_of"] == "2026-04-01"
    assert out["rows"][0]["factor_version"] == "l2-basic-v1"

