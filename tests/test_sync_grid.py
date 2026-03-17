# tests/test_sync_grid.py
from unittest.mock import MagicMock
from sqlmodel import select
from hiveflow.application.sync import sync_from_okx
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.grid_positions import GridPosition
from hiveflow.infrastructure.okx.okx_provider import OkxGridPosition


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/sg.db",
        okx_api_key="k", okx_api_secret="s", okx_api_passphrase="p",
    )


def _provider(positions=None, grid_positions=None) -> MagicMock:
    p = MagicMock()
    p.fetch_positions.return_value = positions or []
    p.fetch_tickers.return_value = []
    p.fetch_candles.return_value = []
    p.fetch_grid_positions.return_value = grid_positions or []
    return p


def test_sync_writes_grid_positions(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    grids = [OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                              base_quantity=0.005, quote_quantity=100.0, state="running")]
    sync_from_okx(provider=_provider(grid_positions=grids), settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(GridPosition)).all()
    assert len(rows) == 1
    assert rows[0].symbol == "BTC"
    assert rows[0].grid_id == "001"


def test_sync_clears_grid_positions_on_each_run(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    g1 = OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                          base_quantity=0.005, quote_quantity=100.0, state="running")
    sync_from_okx(provider=_provider(grid_positions=[g1]), settings=settings)
    sync_from_okx(provider=_provider(grid_positions=[]), settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(GridPosition)).all()
    assert len(rows) == 0


def test_sync_result_includes_grid_count(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    grids = [
        OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                        base_quantity=0.005, quote_quantity=100.0, state="running"),
        OkxGridPosition(symbol="ETH", grid_id="002", inst_id="ETH-USDT",
                        base_quantity=0.1, quote_quantity=50.0, state="running"),
    ]
    result = sync_from_okx(provider=_provider(grid_positions=grids), settings=settings)
    assert result.grids_synced == 2
