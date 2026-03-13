import json
from pathlib import Path

from typer.testing import CliRunner

from hiveflow.cli import app


def test_backtest_commands_are_available() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "--help"])
    assert result.exit_code == 0


def test_backtest_run_and_list_support_json(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "cli-backtest.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    strategies_csv = tmp_path / "strategies.csv"
    strategies_csv.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势|动量,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_csv), "--mode", "replace"])

    targets_csv = tmp_path / "targets.csv"
    targets_csv.write_text(
        (
            "strategy_name,symbol,target_weight\n"
            "进攻突破策略,BTC,0.6\n"
            "进攻突破策略,ETH,0.4\n"
        ),
        encoding="utf-8",
    )
    runner.invoke(app, ["targets", "import", "--file", str(targets_csv), "--mode", "replace"])

    prices_csv = tmp_path / "prices.csv"
    prices_csv.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T00:00:00Z,100,110,90,100,1000\n"
            "ETH,2026-03-13T00:00:00Z,50,55,45,50,2000\n"
            "BTC,2026-03-13T01:00:00Z,100,112,98,110,1200\n"
            "ETH,2026-03-13T01:00:00Z,50,60,49,55,2300\n"
        ),
        encoding="utf-8",
    )

    run_result = runner.invoke(
        app,
        [
            "backtest",
            "run",
            "--strategy",
            "进攻突破策略",
            "--file",
            str(prices_csv),
            "--output",
            "json",
        ],
    )
    assert run_result.exit_code == 0
    payload = json.loads(run_result.stdout)
    assert payload["strategy_name"] == "进攻突破策略"

    list_result = runner.invoke(
        app, ["backtest", "list", "--strategy", "进攻突破策略", "--output", "json"]
    )
    assert list_result.exit_code == 0
    items = json.loads(list_result.stdout)
    assert len(items) == 1
