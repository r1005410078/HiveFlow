"""A 股行情同步与持仓导入测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.domain.market import CN_A_SHARE


# ------------------------------------------------------------------ #
# Chunk 2 Task 6 — cn_sync
# ------------------------------------------------------------------ #

def _fake_bars(symbol: str = "000001.SZ"):
    from datetime import datetime, timezone
    from hiveflow.domain.market_data import MarketBar
    return [
        MarketBar(
            symbol=symbol,
            timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            open=10.0 + i,
            high=11.0 + i,
            low=9.0 + i,
            close=10.5 + i,
            volume=1_000_000.0,
            market=CN_A_SHARE,
        )
        for i in range(3)
    ]


def test_sync_cn_market_data_writes_bars_to_db(tmp_path: Path) -> None:
    """sync_cn_market_data 应将 MarketBar 写入数据库。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="akshare")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars("000001.SZ")

    with patch(
        "hiveflow.application.cn_sync.CNMarketDataProvider",
        return_value=fake_provider,
    ):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(
            symbols=["000001.SZ"], days=30, settings=settings
        )

    assert result.imported == 3
    assert result.symbols == ["000001.SZ"]

    with get_session(settings) as session:
        bars = session.exec(
            select(MarketBar).where(MarketBar.symbol == "000001.SZ")
        ).all()
    assert len(bars) == 3
    assert all(b.market == CN_A_SHARE for b in bars)


def test_sync_cn_market_data_result_fields(tmp_path: Path) -> None:
    """result 包含 imported / symbols / source 字段。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="tushare", tushare_token="tok")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars()

    with patch("hiveflow.application.cn_sync.CNMarketDataProvider", return_value=fake_provider):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(symbols=["000001.SZ"], days=7, settings=settings)

    assert result.source == "tushare"
    assert "000001.SZ" in result.symbols
    d = result.to_dict()
    assert "imported" in d
    assert "symbols" in d
    assert "source" in d
