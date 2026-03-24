# src/hiveflow/application/cn_signals.py
"""A 股特有信号应用层函数：拉取并落库个股/市场级信号。"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.cn_signals import CNMarketSignal, CNStockSignal
from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider


def build_cn_stock_signal(
    symbol: str,
    settings: Settings | None = None,
) -> CNStockSignal:
    """拉取个股 A 股特有信号并落库（同一 symbol 同一日期覆盖写入）。"""
    s = settings or Settings()
    create_all_tables(s)

    provider = CNSignalProvider(settings=s)
    data = provider.fetch_stock_signal(symbol)
    date = datetime.now().strftime("%Y-%m-%d")

    entity = CNStockSignal(
        symbol=symbol,
        date=date,
        timestamp=data["timestamp"],
        pe_ratio=data.get("pe_ratio"),
        pb_ratio=data.get("pb_ratio"),
        limit_up_hit=data.get("limit_up_hit"),
        limit_down_hit=data.get("limit_down_hit"),
    )

    with get_session(s) as session:
        existing = session.exec(
            select(CNStockSignal).where(
                CNStockSignal.symbol == symbol,
                CNStockSignal.date == date,
            )
        ).all()
        for old in existing:
            session.delete(old)
        session.flush()
        session.add(entity)
        session.commit()
        session.refresh(entity)

    return entity


def build_cn_market_signal(
    settings: Settings | None = None,
) -> CNMarketSignal:
    """拉取市场级 A 股信号并落库（同一日期覆盖写入）。"""
    s = settings or Settings()
    create_all_tables(s)

    provider = CNSignalProvider(settings=s)
    data = provider.fetch_market_signal()
    date = datetime.now().strftime("%Y-%m-%d")

    entity = CNMarketSignal(
        date=date,
        timestamp=data["timestamp"],
        northbound_net_flow=data.get("northbound_net_flow"),
        margin_balance=data.get("margin_balance"),
        limit_up_count=data.get("limit_up_count"),
        limit_down_count=data.get("limit_down_count"),
    )

    with get_session(s) as session:
        existing = session.exec(
            select(CNMarketSignal).where(CNMarketSignal.date == date)
        ).all()
        for old in existing:
            session.delete(old)
        session.flush()
        session.add(entity)
        session.commit()
        session.refresh(entity)

    return entity
