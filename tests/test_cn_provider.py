# tests/test_cn_provider.py
"""CNMarketDataProvider mock 测试（不依赖真实外部 API）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.domain.market import CN_A_SHARE


def _make_akshare_df(symbol: str):
    """构造 akshare stock_zh_a_hist 返回的 DataFrame 格式。"""
    import pandas as pd
    return pd.DataFrame({
        "日期": ["2026-01-01", "2026-01-02"],
        "开盘": [10.0, 10.5],
        "最高": [10.8, 11.0],
        "最低": [9.9, 10.3],
        "收盘": [10.5, 10.8],
        "成交量": [1000000, 1200000],
    })


def test_cn_provider_akshare_returns_market_bars(tmp_path: Path) -> None:
    """akshare 后端返回 MarketBar 列表，market 字段为 cn_a_share。

    patch 路径为模块级属性 `hiveflow.infrastructure.cn_market_data_provider.akshare`，
    实现中通过 `_self_mod.akshare` 访问，使 mock 生效。
    """
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod

    mock_ak = MagicMock()
    mock_ak.stock_zh_a_hist.return_value = _make_akshare_df("000001")

    original = provider_mod.akshare
    provider_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="akshare")
        bars = provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.akshare = original

    assert len(bars) == 2
    for bar in bars:
        assert bar.market == CN_A_SHARE
        assert bar.symbol == "000001.SZ"
        assert bar.close > 0


def test_cn_provider_tushare_returns_market_bars(tmp_path: Path) -> None:
    """tushare 后端返回相同格式的 MarketBar 列表。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod

    mock_df = pd.DataFrame({
        "trade_date": ["20260101", "20260102"],
        "open": [10.0, 10.5],
        "high": [10.8, 11.0],
        "low": [9.9, 10.3],
        "close": [10.5, 10.8],
        "vol": [1000000.0, 1200000.0],
    })
    mock_pro = MagicMock()
    mock_pro.daily.return_value = mock_df
    mock_ts = MagicMock()
    mock_ts.pro_api.return_value = mock_pro

    original = provider_mod.tushare
    provider_mod.tushare = mock_ts
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="tushare", token="fake_token")
        bars = provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.tushare = original

    assert len(bars) == 2
    for bar in bars:
        assert bar.market == CN_A_SHARE
        assert bar.symbol == "000001.SZ"


def test_cn_provider_unsupported_source_raises() -> None:
    """不支持的 source 在 fetch_bars 时应抛出 ValueError。"""
    from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
    provider = CNMarketDataProvider(source="unknown_source")
    with pytest.raises(ValueError, match="不支持的数据源"):
        provider.fetch_bars(["000001.SZ"], days=5)


def test_cn_provider_missing_akshare_raises_import_error() -> None:
    """模块级 akshare=None 时，fetch_bars 应抛出 ImportError 并提示安装方法。"""
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod
    original = provider_mod.akshare
    provider_mod.akshare = None  # 模拟未安装
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="akshare")
        with pytest.raises(ImportError, match="akshare"):
            provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.akshare = original


def test_to_tencent_code() -> None:
    """_to_tencent_code 转换各交易所格式。"""
    from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
    p = CNMarketDataProvider(source="tencent")
    assert p._to_tencent_code("000001.SZ") == "sz000001"
    assert p._to_tencent_code("600000.SH") == "sh600000"
    assert p._to_tencent_code("830017.BJ") == "bj830017"
    # 无后缀：按首位推断
    assert p._to_tencent_code("600584") == "sh600584"
    assert p._to_tencent_code("002050") == "sz002050"


def _make_tencent_response(
    code: str = "000001",
    close: str = "12.34",
    open_: str = "12.10",
    high: str = "13.00",
    low: str = "11.80",
    volume: str = "100",  # 手
    ts: str = "20260324150000",
) -> bytes:
    """构造腾讯行情接口的模拟响应（GBK 编码）。"""
    # 35 个字段，只填写关键位置，其余用空字符串
    parts = [""] * 45
    parts[1] = "平安银行"
    parts[2] = code
    parts[3] = close
    parts[5] = open_
    parts[6] = volume
    parts[30] = ts
    parts[33] = high
    parts[34] = low
    data = "~".join(parts)
    line = f'v_sz{code}="{data}";\n'
    return line.encode("gbk")


def test_cn_provider_tencent_parses_mock_response(monkeypatch) -> None:
    """tencent 后端：mock HTTP 响应，验证字段解析正确。"""
    import io
    from unittest.mock import MagicMock
    import urllib.request
    from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
    from hiveflow.domain.market import CN_A_SHARE

    mock_body = _make_tencent_response()

    class _FakeResp:
        def read(self):
            return mock_body
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _FakeResp())

    provider = CNMarketDataProvider(source="tencent")
    bars = provider.fetch_bars(["000001.SZ"], days=1)

    assert len(bars) == 1
    bar = bars[0]
    assert bar.close == 12.34
    assert bar.open == 12.10
    assert bar.high == 13.00
    assert bar.low == 11.80
    assert bar.volume == 10000.0  # 100手 × 100
    assert bar.market == CN_A_SHARE
    assert bar.symbol == "000001.SZ"


def test_cn_provider_tencent_network_error_returns_empty(monkeypatch) -> None:
    """tencent 后端：网络异常时返回空列表，不抛出。"""
    import urllib.request
    from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("timeout"))
    )

    provider = CNMarketDataProvider(source="tencent")
    bars = provider.fetch_bars(["000001.SZ"], days=1)
    assert bars == []


def test_cn_provider_akshare_retries_and_recovers() -> None:
    """akshare 首次失败后应自动重试，后续成功则返回数据。"""
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod

    mock_ak = MagicMock()
    mock_ak.stock_zh_a_hist.side_effect = [
        ConnectionError("temporary network issue"),
        _make_akshare_df("000001"),
    ]

    original = provider_mod.akshare
    provider_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="akshare")
        bars = provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.akshare = original

    assert len(bars) == 2
    assert mock_ak.stock_zh_a_hist.call_count == 2
