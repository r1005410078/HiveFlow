import pandas as pd

from hiveflow.universe.application.filter_use_case import filter_universe


def test_filter_universe_rules():
    """验证 L0 过滤规则能排除不满足条件的标的。"""
    df = pd.DataFrame(
        [
            {"symbol": "000001.SZ", "is_st": False, "is_suspended": False, "listed_days": 120},
            {"symbol": "000002.SZ", "is_st": True, "is_suspended": False, "listed_days": 120},
        ]
    )
    out = filter_universe(df)
    assert list(out["symbol"]) == ["000001.SZ"]
