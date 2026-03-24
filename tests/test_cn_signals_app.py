# tests/test_cn_signals_app.py
"""应用层 build_cn_stock_signal / build_cn_market_signal 测试。"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.config import Settings


def _make_settings(tmp_path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db")


def _stock_signal_dict() -> dict:
    return {
        "limit_up_hit": True,
        "limit_down_hit": False,
        "pe_ratio": 12.5,
        "pb_ratio": 1.3,
        "timestamp": datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc),
    }


def _market_signal_dict() -> dict:
    return {
        "northbound_net_flow": 88.3,
        "margin_balance": 21000.0,
        "limit_up_count": 45,
        "limit_down_count": 12,
        "timestamp": datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc),
    }


# ------------------------------------------------------------------ #
# build_cn_stock_signal
# ------------------------------------------------------------------ #

def test_build_cn_stock_signal_success(tmp_path) -> None:
    """正常路径：返回 CNStockSignal 实体，字段正确。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_stock_signal.return_value = _stock_signal_dict()

        from hiveflow.application.cn_signals import build_cn_stock_signal
        result = build_cn_stock_signal("000001.SZ", settings=settings)

    assert result.symbol == "000001.SZ"
    assert result.pe_ratio == 12.5
    assert result.pb_ratio == 1.3
    assert result.limit_up_hit is True
    assert result.limit_down_hit is False
    assert result.market == "cn_a_share"
    assert result.id is not None


def test_build_cn_stock_signal_dedup(tmp_path) -> None:
    """同一 symbol 同一日期重复调用，覆盖写入不重复堆积。"""
    from hiveflow.db import create_all_tables
    from sqlmodel import Session, select
    from hiveflow.domain.cn_signals import CNStockSignal

    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_stock_signal.return_value = _stock_signal_dict()

        from hiveflow.application.cn_signals import build_cn_stock_signal

        # 调用两次
        build_cn_stock_signal("000001.SZ", settings=settings)
        build_cn_stock_signal("000001.SZ", settings=settings)

    from hiveflow.db import get_engine
    engine = get_engine(settings)
    with Session(engine) as session:
        rows = session.exec(
            select(CNStockSignal).where(CNStockSignal.symbol == "000001.SZ")
        ).all()

    assert len(rows) == 1


def test_build_cn_stock_signal_uses_provider_with_settings(tmp_path) -> None:
    """CNSignalProvider 以 settings 构造，fetch_stock_signal 传入正确 symbol。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_stock_signal.return_value = _stock_signal_dict()

        from hiveflow.application.cn_signals import build_cn_stock_signal
        build_cn_stock_signal("600000.SH", settings=settings)

        MockProvider.assert_called_once_with(settings=settings)
        instance.fetch_stock_signal.assert_called_once_with("600000.SH")


# ------------------------------------------------------------------ #
# build_cn_market_signal
# ------------------------------------------------------------------ #

def test_build_cn_market_signal_success(tmp_path) -> None:
    """market signal 正常路径：返回 CNMarketSignal 实体，字段正确。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_market_signal.return_value = _market_signal_dict()

        from hiveflow.application.cn_signals import build_cn_market_signal
        result = build_cn_market_signal(settings=settings)

    assert result.northbound_net_flow == 88.3
    assert result.margin_balance == 21000.0
    assert result.limit_up_count == 45
    assert result.limit_down_count == 12
    assert result.id is not None


def test_build_cn_market_signal_dedup(tmp_path) -> None:
    """同一日期重复调用，覆盖写入不重复堆积。"""
    from hiveflow.db import create_all_tables
    from sqlmodel import Session, select
    from hiveflow.domain.cn_signals import CNMarketSignal

    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_market_signal.return_value = _market_signal_dict()

        from hiveflow.application.cn_signals import build_cn_market_signal

        build_cn_market_signal(settings=settings)
        build_cn_market_signal(settings=settings)

    from hiveflow.db import get_engine
    engine = get_engine(settings)
    with Session(engine) as session:
        rows = session.exec(select(CNMarketSignal)).all()

    assert len(rows) == 1


def test_build_cn_market_signal_uses_provider(tmp_path) -> None:
    """CNSignalProvider 以 settings 构造，fetch_market_signal 被调用。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_market_signal.return_value = _market_signal_dict()

        from hiveflow.application.cn_signals import build_cn_market_signal
        build_cn_market_signal(settings=settings)

        MockProvider.assert_called_once_with(settings=settings)
        instance.fetch_market_signal.assert_called_once()


# ------------------------------------------------------------------ #
# 补全缺失场景
# ------------------------------------------------------------------ #

def test_build_cn_stock_signal_tencent_fallback(tmp_path) -> None:
    """akshare fallback 成功后，应用层收到 limit_up_hit=True / limit_down_hit=False。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_stock_signal.return_value = {
            "limit_up_hit": True,
            "limit_down_hit": False,
            "pe_ratio": None,
            "pb_ratio": None,
            "timestamp": datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc),
        }

        from hiveflow.application.cn_signals import build_cn_stock_signal
        result = build_cn_stock_signal("000001.SZ", settings=settings)

    assert result.limit_up_hit is True
    assert result.limit_down_hit is False


def test_build_cn_stock_signal_all_fail(tmp_path) -> None:
    """所有数据源失败时，字段均为 None，不抛异常。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_stock_signal.return_value = {
            "pe_ratio": None,
            "pb_ratio": None,
            "limit_up_hit": None,
            "limit_down_hit": None,
            "timestamp": datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc),
        }

        from hiveflow.application.cn_signals import build_cn_stock_signal
        result = build_cn_stock_signal("000001.SZ", settings=settings)

    assert result.pe_ratio is None
    assert result.pb_ratio is None
    assert result.limit_up_hit is None
    assert result.limit_down_hit is None


def test_build_cn_market_signal_partial_none(tmp_path) -> None:
    """部分字段为 None 时，返回实体字段正确保留 None。"""
    from hiveflow.db import create_all_tables
    settings = _make_settings(tmp_path)
    create_all_tables(settings)

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider"
    ) as MockProvider:
        instance = MockProvider.return_value
        instance.fetch_market_signal.return_value = {
            "northbound_net_flow": 32.5,
            "margin_balance": None,
            "limit_up_count": 43,
            "limit_down_count": None,
            "timestamp": datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc),
        }

        from hiveflow.application.cn_signals import build_cn_market_signal
        result = build_cn_market_signal(settings=settings)

    assert result.northbound_net_flow == 32.5
    assert result.margin_balance is None
    assert result.limit_up_count == 43
    assert result.limit_down_count is None
