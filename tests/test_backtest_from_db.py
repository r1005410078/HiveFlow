# tests/test_backtest_from_db.py
import json
from datetime import datetime, timezone
from typer.testing import CliRunner
from sqlmodel import select
from hiveflow.application.backtest import run_backtest_for_strategy
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.market_data import MarketBar


def _setup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/bt.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        # 目标配比
        s.add(TargetAllocation(strategy_name="test_strat", symbol="BTC", target_weight=0.6))
        s.add(TargetAllocation(strategy_name="test_strat", symbol="ETH", target_weight=0.4))
        # 行情数据（7 天）
        for i in range(7):
            ts = datetime(2026, 3, i + 1, tzinfo=timezone.utc)
            s.add(MarketBar(symbol="BTC", timestamp=ts,
                            open=70000.0, high=71000.0, low=69000.0,
                            close=70000.0 + i * 100, volume=100.0))
            s.add(MarketBar(symbol="ETH", timestamp=ts,
                            open=3000.0, high=3100.0, low=2900.0,
                            close=3000.0 + i * 10, volume=500.0))
        s.commit()
    return settings


def test_backtest_run_from_db(tmp_path) -> None:
    settings = _setup(tmp_path)
    result = run_backtest_for_strategy(
        strategy_name="test_strat",
        prices_file=None,
        settings=settings,
    )
    assert result.periods > 0
    assert result.prices_file == "DB:MarketBar"
    assert result.weights_snapshot is not None
    snapshot = json.loads(result.weights_snapshot)
    assert snapshot["BTC"] == 0.6
    assert snapshot["ETH"] == 0.4


def test_backtest_run_stores_weights_snapshot(tmp_path) -> None:
    settings = _setup(tmp_path)
    run_backtest_for_strategy(strategy_name="test_strat", prices_file=None, settings=settings)
    with get_session(settings) as s:
        row = s.exec(select(BacktestResult)).first()
    assert row is not None
    assert row.weights_snapshot is not None
    assert json.loads(row.weights_snapshot)["BTC"] == 0.6


def test_backtest_run_db_cli(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["backtest", "run", "--strategy", "test_strat"])
    assert result.exit_code == 0
    assert "回测完成" in result.output


def test_backtest_list_includes_id(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    CliRunner().invoke(app, ["backtest", "run", "--strategy", "test_strat"])
    result = CliRunner().invoke(app, ["backtest", "list", "--output", "json"])
    data = json.loads(result.output)
    assert len(data) >= 1
    assert "id" in data[0]
    assert data[0]["id"] is not None
