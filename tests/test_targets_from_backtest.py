import json
import pytest
from typer.testing import CliRunner
from sqlmodel import select
from hiveflow.application.backtest import set_targets_from_backtest
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult


def _setup_with_backtest(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/t.db")
    create_all_tables(settings)
    snapshot = json.dumps({"BTC": 0.4, "ETH": 0.3, "USDT": 0.3})
    with get_session(settings) as s:
        row = BacktestResult(
            strategy_name="均衡版",
            prices_file="DB:MarketBar",
            periods=30,
            total_return=0.15,
            max_drawdown=-0.12,
            sharpe=1.2,
            weights_snapshot=snapshot,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return settings, row.id


def test_set_targets_writes_allocations(tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    set_targets_from_backtest(backtest_id=bt_id, settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "均衡版"
        )).all()
    weights = {r.symbol: r.target_weight for r in rows}
    assert abs(weights["BTC"] - 0.4) < 0.001
    assert abs(weights["ETH"] - 0.3) < 0.001
    assert abs(weights["USDT"] - 0.3) < 0.001


def test_set_targets_replaces_existing(tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    with get_session(settings) as s:
        s.add(TargetAllocation(strategy_name="均衡版", symbol="SOL", target_weight=0.5))
        s.commit()
    set_targets_from_backtest(backtest_id=bt_id, settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "均衡版"
        )).all()
    symbols = {r.symbol for r in rows}
    assert "SOL" not in symbols  # 旧记录应被清除


def test_set_targets_cli(monkeypatch, tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["targets", "set-from-backtest", str(bt_id)])
    assert result.exit_code == 0
    assert "BTC" in result.output
    assert "40" in result.output


def test_set_targets_fails_on_missing_snapshot(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/t2.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        row = BacktestResult(
            strategy_name="test", prices_file="f.csv",
            periods=10, total_return=0.1, max_drawdown=-0.05, sharpe=1.0,
            weights_snapshot=None,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        bt_id = row.id
    with pytest.raises(ValueError, match="weights_snapshot"):
        set_targets_from_backtest(backtest_id=bt_id, settings=settings)
