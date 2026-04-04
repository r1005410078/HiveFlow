"""AkshareUniverseAdapter: symbol + Chinese name extraction from DataFrame."""

from __future__ import annotations

import pandas as pd

from interfaces.adapters.market_data.akshare_universe_adapter import AkshareUniverseAdapter


def test_symbol_name_pairs_from_index_style_df() -> None:
    ad = AkshareUniverseAdapter.__new__(AkshareUniverseAdapter)
    df = pd.DataFrame(
        {
            "成分券代码": ["600519", "000001"],
            "品种名称": ["贵州茅台", "平安银行"],
        }
    )
    pairs = ad._symbol_name_pairs_from_df(df)
    assert pairs == [("600519.SH", "贵州茅台"), ("000001.SZ", "平安银行")]


def test_symbol_name_pairs_missing_name_column() -> None:
    ad = AkshareUniverseAdapter.__new__(AkshareUniverseAdapter)
    df = pd.DataFrame({"代码": ["600519"]})
    pairs = ad._symbol_name_pairs_from_df(df)
    assert pairs == [("600519.SH", "")]
