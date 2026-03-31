import pandas as pd

from hiveflow.signal.application.normalize_use_case import winsorize_then_zscore


def test_winsorize_then_zscore_len():
    """验证 L3 信号标准化不改变样本长度。"""
    out = winsorize_then_zscore(pd.Series([1, 2, 3, 100]))
    assert len(out) == 4
