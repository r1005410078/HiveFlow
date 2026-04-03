import pandas as pd

from application.factor.basic_factor_service import compute_raw_factor_values_from_bar_rows
from hiveflow.factor.application.compute_use_case import compute_basic_factors


def test_compute_factor_columns():
    """验证 L2 基础因子计算后包含预期因子列（与 basic_factor_service 共用公式）。"""
    df = pd.DataFrame({"close": [10 + i * 0.1 for i in range(30)], "turnover": [0.02] * 30})
    out = compute_basic_factors(df)
    assert {"momentum_20", "inv_volatility_20", "turnover_rate"}.issubset(out.columns)


def test_compute_basic_factors_last_row_matches_bar_snapshot_formula() -> None:
    df = pd.DataFrame(
        {"close": [10 + i * 0.05 for i in range(70)], "turnover": [1000.0 + i for i in range(70)]}
    )
    out = compute_basic_factors(df)
    bars = [
        {
            "symbol": "_frame",
            "bar_time": f"{i:06d}",
            "close": float(df["close"].iloc[i]),
            "volume": float(df["turnover"].iloc[i]),
        }
        for i in range(70)
    ]
    expected = compute_raw_factor_values_from_bar_rows(bars)
    assert expected is not None
    last = 69
    for name, val in expected.items():
        got = float(out.iloc[last][name])
        assert abs(got - val) < 1e-5, f"{name}: got {got} expected {val}"
