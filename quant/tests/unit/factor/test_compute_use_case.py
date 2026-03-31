import pandas as pd

from hiveflow.factor.application.compute_use_case import compute_basic_factors


def test_compute_factor_columns():
    """验证 L2 基础因子计算后包含预期因子列。"""
    df = pd.DataFrame({"close": [10 + i * 0.1 for i in range(30)], "turnover": [0.02] * 30})
    out = compute_basic_factors(df)
    assert {"momentum_20", "inv_volatility_20", "turnover_rate"}.issubset(out.columns)
