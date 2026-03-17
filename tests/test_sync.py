# tests/test_sync.py
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlmodel import select

from hiveflow.application.sync import SyncResult, sync_from_okx
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError, OkxCandle, OkxPosition, OkxTicker,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/sync.db",
        okx_api_key="k", okx_api_secret="s", okx_api_passphrase="p",
    )


def _provider(positions=None, tickers=None, candles=None) -> MagicMock:
    p = MagicMock()
    p.fetch_positions.return_value = positions or []
    p.fetch_tickers.return_value = tickers or []
    p.fetch_candles.return_value = candles or []
    p.fetch_grid_positions.return_value = []
    return p


def test_sync_writes_positions(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    okx_pos = [
        OkxPosition(symbol="BTC", quantity=0.5, market_value_usdt=20000.0),
        OkxPosition(symbol="ETH", quantity=3.0, market_value_usdt=9000.0),
    ]
    result = sync_from_okx(provider=_provider(positions=okx_pos), settings=settings)
    assert result.positions_synced == 2
    with get_session(settings) as s:
        rows = s.exec(select(Position)).all()
    assert {r.symbol for r in rows} == {"BTC", "ETH"}
    btc = next(r for r in rows if r.symbol == "BTC")
    assert abs(btc.weight - 20000 / 29000) < 0.001


def test_sync_writes_tickers_as_market_bars(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    positions = [OkxPosition(symbol="BTC", quantity=0.5, market_value_usdt=20000.0)]
    tickers = [OkxTicker(symbol="BTC", last=70000, open24h=68000, high24h=71000, low24h=67000, vol24h=500)]
    result = sync_from_okx(provider=_provider(positions=positions, tickers=tickers), settings=settings)
    assert result.prices_synced == 1
    with get_session(settings) as s:
        rows = s.exec(select(MarketBar)).all()
    assert len(rows) == 1
    assert rows[0].close == 70000.0


def test_sync_writes_historical_candles(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    ts = datetime(2026, 3, 15, tzinfo=timezone.utc)
    positions = [OkxPosition(symbol="BTC", quantity=0.5, market_value_usdt=20000.0)]
    candles = [OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70500, volume=100)]
    result = sync_from_okx(provider=_provider(positions=positions, candles=candles), settings=settings, days=7)
    assert result.candles_synced == 1


def test_sync_is_atomic_on_error(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    provider = MagicMock()
    provider.fetch_positions.side_effect = OkxAuthError("鉴权失败")
    with pytest.raises(OkxAuthError):
        sync_from_okx(provider=provider, settings=settings)
    with get_session(settings) as s:
        assert len(s.exec(select(Position)).all()) == 0


def test_sync_upserts_candles(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    ts = datetime(2026, 3, 15, tzinfo=timezone.utc)
    positions = [OkxPosition(symbol="BTC", quantity=0.5, market_value_usdt=20000.0)]
    c1 = OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70000, volume=100)
    c2 = OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70999, volume=200)
    sync_from_okx(provider=_provider(positions=positions, candles=[c1]), settings=settings, days=1)
    sync_from_okx(provider=_provider(positions=positions, candles=[c2]), settings=settings, days=1)
    with get_session(settings) as s:
        rows = s.exec(select(MarketBar)).all()
    assert len(rows) == 1
    assert rows[0].close == 70999.0
