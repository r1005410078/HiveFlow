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
