# tests/test_positions_list_grid.py
from typer.testing import CliRunner
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.grid_positions import GridPosition
from hiveflow.domain.positions import Position
import json


def _setup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/p.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        s.add(Position(symbol="BTC", quantity=0.001, market_value=700.0, weight=0.7))
        s.add(GridPosition(symbol="ETH", grid_id="001", inst_id="ETH-USDT",
                           base_quantity=0.1, quote_quantity=50.0, state="running"))
        s.commit()
    return settings


def test_positions_list_shows_grid_section(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list"])
    assert result.exit_code == 0
    assert "自由持仓" in result.output
    assert "网格持仓" in result.output
    assert "ETH" in result.output


def test_positions_list_json_includes_grid(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "free" in data
    assert "grid" in data
    assert data["grid"][0]["symbol"] == "ETH"


def test_positions_list_no_grid_section_when_empty(monkeypatch, tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/p2.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        s.add(Position(symbol="BTC", quantity=0.001, market_value=700.0, weight=1.0))
        s.commit()
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list"])
    assert result.exit_code == 0
    assert "网格持仓" not in result.output
