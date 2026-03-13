from pathlib import Path

from hiveflow.application.backtest import list_backtest_results
from hiveflow.application.backtest import run_backtest_for_strategy
from hiveflow.application.strategies import import_strategies_from_csv
from hiveflow.application.targets import import_target_allocations_from_csv


def test_run_backtest_for_strategy_persists_result(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "backtest.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")

    strategies_csv = tmp_path / "strategies.csv"
    strategies_csv.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势|动量,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    import_strategies_from_csv(file=strategies_csv, mode="replace")

    targets_csv = tmp_path / "targets.csv"
    targets_csv.write_text(
        (
            "strategy_name,symbol,target_weight\n"
            "进攻突破策略,BTC,0.6\n"
            "进攻突破策略,ETH,0.4\n"
        ),
        encoding="utf-8",
    )
    import_target_allocations_from_csv(file=targets_csv, mode="replace")

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

    result = run_backtest_for_strategy(strategy_name="进攻突破策略", prices_file=prices_csv)
    assert result.strategy_name == "进攻突破策略"
    assert result.periods >= 1
    assert result.total_return > 0
    assert result.max_drawdown <= 0

    rows = list_backtest_results(strategy_name="进攻突破策略")
    assert len(rows) == 1
    assert rows[0].strategy_name == "进攻突破策略"
