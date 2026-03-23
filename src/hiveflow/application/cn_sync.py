"""A 股行情同步应用服务。"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar
from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider


@dataclass(frozen=True)
class CNSyncResult:
    """A 股行情同步结果。"""
    imported: int
    symbols: list[str]
    source: str

    def to_dict(self) -> dict:
        return {
            "imported": self.imported,
            "symbols": self.symbols,
            "source": self.source,
        }


def sync_cn_market_data(
    symbols: list[str],
    days: int,
    settings: Settings | None = None,
) -> CNSyncResult:
    """使用 CNMarketDataProvider 拉取 A 股行情并写入 MarketBar 表。

    market 字段由 CNMarketDataProvider 自动填充为 'cn_a_share'。
    重复记录（同 symbol + timestamp）覆盖写入：先删除旧记录再插入。
    """
    s = settings or Settings()
    create_all_tables(s)

    provider = CNMarketDataProvider(source=s.cn_market_data_source, token=s.tushare_token)
    bars = provider.fetch_bars(symbols, days)

    with get_session(s) as session:
        for bar in bars:
            # 覆盖写入：删除相同 symbol + timestamp 的旧记录
            existing = session.exec(
                select(MarketBar).where(
                    MarketBar.symbol == bar.symbol,
                    MarketBar.timestamp == bar.timestamp,
                )
            ).all()
            for old in existing:
                session.delete(old)
            session.add(bar)
        session.commit()

    return CNSyncResult(
        imported=len(bars),
        symbols=symbols,
        source=s.cn_market_data_source,
    )
