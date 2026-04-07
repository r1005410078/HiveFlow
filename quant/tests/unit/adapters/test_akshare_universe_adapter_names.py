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


def test_symbol_name_pairs_accepts_float_code_like_em_spot() -> None:
    """stock_zh_a_spot_em 等接口常把代码列为 float（600900.0），须能解析。"""
    ad = AkshareUniverseAdapter.__new__(AkshareUniverseAdapter)
    df = pd.DataFrame(
        {
            "代码": [600900.0, 600519.0],
            "名称": ["长江电力", "贵州茅台"],
        }
    )
    pairs = ad._symbol_name_pairs_from_df(df)
    assert ("600900.SH", "长江电力") in pairs
    assert ("600519.SH", "贵州茅台") in pairs


def test_symbol_name_pairs_accepts_code_with_exchange_suffix() -> None:
    ad = AkshareUniverseAdapter.__new__(AkshareUniverseAdapter)
    df = pd.DataFrame({"代码": ["600900.SH"], "名称": ["长江电力"]})
    pairs = ad._symbol_name_pairs_from_df(df)
    assert pairs == [("600900.SH", "长江电力")]


def test_extract_name_from_individual_info_df() -> None:
    ad = AkshareUniverseAdapter.__new__(AkshareUniverseAdapter)
    df = pd.DataFrame(
        {
            "item": ["股票代码", "股票简称", "所属行业"],
            "value": ["600900", "长江电力", "电力"],
        }
    )
    assert ad._extract_name_from_individual_info_df(df) == "长江电力"
