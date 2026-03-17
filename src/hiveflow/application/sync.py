# src/hiveflow/application/sync.py
"""OKX 数据同步用例。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.grid_positions import GridPosition
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.okx.okx_provider import OkxProvider


@dataclass(frozen=True)
class SyncResult:
    synced_at: datetime
    positions_synced: int
    prices_synced: int
    candles_synced: int
    total_value_usdt: float
    grids_synced: int = 0

    def to_dict(self) -> dict:
        return {
            "synced_at": self.synced_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "positions_synced": self.positions_synced,
            "prices_synced": self.prices_synced,
            "candles_synced": self.candles_synced,
            "total_value_usdt": round(self.total_value_usdt, 2),
            "grids_synced": self.grids_synced,
        }


def sync_from_okx(
    provider: OkxProvider,
    settings: Settings | None = None,
    days: int | None = None,
) -> SyncResult:
    """从 OKX 拉取数据写入数据库。全成功或全失败（原子性）。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 1. 先拉取所有数据（任一失败在写入前抛出）
    okx_positions = provider.fetch_positions()
    okx_grids = provider.fetch_grid_positions()
    # USDT 本身不需要拉 ticker（价格恒为 1），跳过避免无效请求
    inst_ids = [f"{p.symbol}-USDT" for p in okx_positions if p.symbol != "USDT"]

    okx_tickers = provider.fetch_tickers(inst_ids) if inst_ids else []

    okx_candles = []
    if days is not None and inst_ids:
        for inst_id in inst_ids:
            okx_candles.extend(provider.fetch_candles(inst_id, days=days))

    # 2. 全部成功后单事务写入
    total_value = sum(p.market_value_usdt for p in okx_positions)
    now = datetime.now(tz=timezone.utc)

    with get_session(app_settings) as session:
        # 持仓：全量替换
        session.exec(delete(Position))
        for p in okx_positions:
            weight = p.market_value_usdt / total_value if total_value > 0 else 0.0
            session.add(Position(
                symbol=p.symbol, quantity=p.quantity,
                market_value=p.market_value_usdt, weight=weight,
            ))

        # 当前价格：以今天 UTC 零点为时间戳写入 MarketBar（upsert）
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for t in okx_tickers:
            session.exec(
                delete(MarketBar).where(
                    (MarketBar.symbol == t.symbol) & (MarketBar.timestamp == today)
                )
            )
            session.add(MarketBar(
                symbol=t.symbol, timestamp=today,
                open=t.open24h, high=t.high24h, low=t.low24h,
                close=t.last, volume=t.vol24h,
            ))

        # 历史 K 线：按 (symbol, timestamp) upsert
        for c in okx_candles:
            session.exec(
                delete(MarketBar).where(
                    (MarketBar.symbol == c.symbol) & (MarketBar.timestamp == c.timestamp)
                )
            )
            session.add(MarketBar(
                symbol=c.symbol, timestamp=c.timestamp,
                open=c.open, high=c.high, low=c.low,
                close=c.close, volume=c.volume,
            ))

        # 网格持仓：全量替换
        session.exec(delete(GridPosition))
        for g in okx_grids:
            session.add(GridPosition(
                symbol=g.symbol, grid_id=g.grid_id, inst_id=g.inst_id,
                base_quantity=g.base_quantity, quote_quantity=g.quote_quantity,
                state=g.state,
            ))

        session.commit()

    return SyncResult(
        synced_at=now,
        positions_synced=len(okx_positions),
        prices_synced=len(okx_tickers),
        candles_synced=len(okx_candles),
        total_value_usdt=total_value,
        grids_synced=len(okx_grids),
    )
