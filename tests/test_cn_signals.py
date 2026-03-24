# tests/test_cn_signals.py
"""A 股特有信号实体测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hiveflow.domain.cn_signals import CNMarketSignal, CNStockSignal


def test_cn_stock_signal_defaults() -> None:
    """CNStockSignal 默认值正确，market 为 cn_a_share。"""
    ts = datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc)
    sig = CNStockSignal(symbol="000001.SZ", date="2026-03-24", timestamp=ts)
    assert sig.market == "cn_a_share"
    assert sig.pe_ratio is None
    assert sig.pb_ratio is None
    assert sig.limit_up_hit is None
    assert sig.limit_down_hit is None


def test_cn_market_signal_defaults() -> None:
    """CNMarketSignal 默认值正确。"""
    ts = datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc)
    sig = CNMarketSignal(date="2026-03-24", timestamp=ts)
    assert sig.northbound_net_flow is None
    assert sig.margin_balance is None
    assert sig.limit_up_count is None
    assert sig.limit_down_count is None


def test_cn_signal_tables_created(tmp_path) -> None:
    """create_all_tables 后两张新表存在。"""
    import sqlite3
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    conn = sqlite3.connect(str(tmp_path / "hiveflow.db"))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()

    assert "cnstocksignal" in tables
    assert "cnmarketsignal" in tables


def test_tencent_limit_hit_detection() -> None:
    """_detect_limit_from_tencent：涨停/跌停/正常三种情况。"""
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    p = CNSignalProvider()
    # 涨停：last >= prev_close * 1.095
    assert p._detect_limit_from_prices(11.0, 10.0) == (True, False)
    # 跌停：last <= prev_close * 0.905
    assert p._detect_limit_from_prices(9.0, 10.0) == (False, True)
    # 正常
    assert p._detect_limit_from_prices(10.3, 10.0) == (False, False)


def test_to_tencent_code_in_signal_provider() -> None:
    """_to_tencent_code 转换格式正确。"""
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    p = CNSignalProvider()
    assert p._to_tencent_code("000001.SZ") == "sz000001"
    assert p._to_tencent_code("600000.SH") == "sh600000"
    assert p._to_tencent_code("830017.BJ") == "bj830017"


def test_fetch_stock_signal_tencent_success(monkeypatch) -> None:
    """腾讯行情正常时，fetch_stock_signal 返回含涨跌停的 dict。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    # 构造 45 字段腾讯响应：parts[3]=10.50（正常），parts[4]=10.00，parts[30]=时间戳
    parts = [""] * 45
    parts[3] = "10.50"   # last
    parts[4] = "10.00"   # prev_close
    parts[30] = "20260324150000"
    mock_line = 'v_sz000001="' + "~".join(parts) + '";\n'

    class _FakeResp:
        def read(self): return mock_line.encode("gbk")
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _FakeResp())

    p = CNSignalProvider()
    result = p.fetch_stock_signal("000001.SZ")

    assert result["limit_up_hit"] is False
    assert result["limit_down_hit"] is False
    assert result["timestamp"] is not None


def test_fetch_stock_signal_tencent_limit_up(monkeypatch) -> None:
    """last >= prev_close * 1.095 时，limit_up_hit 为 True。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    parts = [""] * 45
    parts[3] = "11.00"   # last（涨停：11.00 >= 10.00 * 1.095）
    parts[4] = "10.00"
    parts[30] = "20260324150000"
    mock_line = 'v_sz000001="' + "~".join(parts) + '";\n'

    class _FakeResp:
        def read(self): return mock_line.encode("gbk")
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _FakeResp())

    p = CNSignalProvider()
    result = p.fetch_stock_signal("000001.SZ")
    assert result["limit_up_hit"] is True
    assert result["limit_down_hit"] is False


def test_fetch_stock_signal_tencent_failure_returns_none_fields(monkeypatch) -> None:
    """腾讯连接失败且 akshare 也失败时，limit 字段为 None，不抛异常。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("timeout"))
    )

    p = CNSignalProvider()
    monkeypatch.setattr(p, "_fetch_limit_hit_akshare", lambda symbol: (None, None))

    result = p.fetch_stock_signal("000001.SZ")
    assert result["limit_up_hit"] is None
    assert result["limit_down_hit"] is None


def test_fetch_stock_signal_tencent_fallback_to_akshare(monkeypatch) -> None:
    """腾讯连接失败时，自动回退至 akshare 并返回涨跌停结果。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("timeout"))
    )

    p = CNSignalProvider()
    monkeypatch.setattr(p, "_fetch_limit_hit_akshare", lambda symbol: (True, False))

    result = p.fetch_stock_signal("000001.SZ")
    assert result["limit_up_hit"] is True
    assert result["limit_down_hit"] is False


# ------------------------------------------------------------------ #
# akshare 后端方法测试
# ------------------------------------------------------------------ #

from unittest.mock import MagicMock  # noqa: E402


def test_fetch_pe_pb_akshare_success() -> None:
    """akshare 返回含 pe/pb 的 DataFrame，正确解析最新行。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_df = pd.DataFrame({"pe": [7.10, 8.32], "pb": [0.65, 0.76]})
    mock_ak = MagicMock()
    mock_ak.stock_a_lg_indicator.return_value = mock_df
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        pe, pb = provider._fetch_pe_pb_akshare("000001.SZ")
    finally:
        mod.akshare = original
    assert pe == 8.32
    assert pb == 0.76


def test_fetch_pe_pb_akshare_strips_suffix() -> None:
    """传入 .SH 后缀时，akshare 收到纯 6 位代码。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_df = pd.DataFrame({"pe": [12.5], "pb": [1.2]})
    mock_ak = MagicMock()
    mock_ak.stock_a_lg_indicator.return_value = mock_df
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        provider._fetch_pe_pb_akshare("600000.SH")
        call_kwargs = mock_ak.stock_a_lg_indicator.call_args
    finally:
        mod.akshare = original
    # 确认传入的 symbol 不含后缀
    passed = call_kwargs[1].get("symbol") or call_kwargs[0][0]
    assert "." not in passed
    assert passed == "600000"


def test_fetch_pe_pb_akshare_failure() -> None:
    """akshare 抛异常时返回 (None, None)。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = MagicMock()
    mock_ak.stock_a_lg_indicator.side_effect = Exception("network error")
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        pe, pb = provider._fetch_pe_pb_akshare("000001.SZ")
    finally:
        mod.akshare = original
    assert pe is None
    assert pb is None


def test_fetch_northbound_akshare_success() -> None:
    """akshare 返回北向资金 DataFrame，正确取最新行净买入值。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_df = pd.DataFrame({"净买入": [12.5, 88.3]})
    mock_ak = MagicMock()
    mock_ak.stock_em_hsgt_north_net_flow_in.return_value = mock_df
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        result = provider._fetch_northbound_akshare()
    finally:
        mod.akshare = original
    assert result == 88.3


def test_fetch_northbound_akshare_failure() -> None:
    """akshare 抛异常时返回 None。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = MagicMock()
    mock_ak.stock_em_hsgt_north_net_flow_in.side_effect = Exception("timeout")
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        result = provider._fetch_northbound_akshare()
    finally:
        mod.akshare = original
    assert result is None


def test_fetch_margin_balance_akshare_success() -> None:
    """akshare 返回沪深融资余额，正确求和返回亿元。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    sh_df = pd.DataFrame({"融资余额": [10000.0, 12000.0]})
    sz_df = pd.DataFrame({"融资余额": [8000.0, 9000.0]})
    mock_ak = MagicMock()
    mock_ak.stock_em_margin_sh.return_value = sh_df
    mock_ak.stock_em_margin_sz.return_value = sz_df
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        result = provider._fetch_margin_balance_akshare()
    finally:
        mod.akshare = original
    # 取各自最新行：12000 + 9000 = 21000 亿元
    assert result == 21000.0


def test_fetch_margin_balance_akshare_failure() -> None:
    """akshare 抛异常时返回 None。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = MagicMock()
    mock_ak.stock_em_margin_sh.side_effect = Exception("error")
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        result = provider._fetch_margin_balance_akshare()
    finally:
        mod.akshare = original
    assert result is None


def test_fetch_limit_counts_akshare_success() -> None:
    """akshare 返回涨跌停统计 DataFrame，正确解析家数。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_df = pd.DataFrame({"涨停家数": [45], "跌停家数": [12]})
    mock_ak = MagicMock()
    mock_ak.stock_limit_up_down_em.return_value = mock_df
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        up, down = provider._fetch_limit_counts_akshare()
    finally:
        mod.akshare = original
    assert up == 45
    assert down == 12


def test_fetch_limit_counts_akshare_failure() -> None:
    """akshare 抛异常时返回 (None, None)。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = MagicMock()
    mock_ak.stock_limit_up_down_em.side_effect = Exception("error")
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        provider = CNSignalProvider()
        up, down = provider._fetch_limit_counts_akshare()
    finally:
        mod.akshare = original
    assert up is None
    assert down is None
