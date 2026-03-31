import pandas as pd

from hiveflow.portfolio.application.allocate_use_case import allocate_weights


def test_allocate_sum_to_one():
    """验证 L4 权重分配结果满足权重和为 1。"""
    out = allocate_weights(pd.DataFrame({"symbol": ["000001.SZ", "000002.SZ"], "signal": [0.7, 0.3]}))
    assert round(out["target_weight"].sum(), 8) == 1.0
