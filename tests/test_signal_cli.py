import json
from datetime import datetime, timedelta, timezone

from sqlmodel import select
from typer.testing import CliRunner

from hiveflow.cli import app
from hiveflow.db import get_session
from hiveflow.db import create_all_tables
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.domain.system_logs import SystemLog


def test_signal_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["signal", "--help"])
    assert result.exit_code == 0


def test_style_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["style", "--help"])
    assert result.exit_code == 0


def test_signal_snapshot_json_returns_strict_failure_and_writes_system_log(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "signal-cli.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(app, ["signal", "snapshot", "--output", "json"])
    assert result.exit_code == 1

    payload = json.loads(result.stdout)
    assert payload["code"] == "E_SIGNAL_REQUIRED_MISSING"
    assert payload["context"] == "signal.snapshot"
    assert payload["trace_id"]
    assert "details" in payload
    assert "missing_signals" in payload["details"]
    assert payload["details"]["strict_mode"] is True

    with get_session() as session:
        rows = session.exec(select(SystemLog)).all()
    assert len(rows) == 1
    assert rows[0].error_code == "E_SIGNAL_REQUIRED_MISSING"
    assert rows[0].context == "signal.snapshot"


def test_style_backtest_rank_json_returns_strict_failure_and_writes_system_log(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "style-cli.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(app, ["style", "backtest-rank", "--output", "json"])
    assert result.exit_code == 1

    payload = json.loads(result.stdout)
    assert payload["code"] == "E_STYLE_EVAL_FAILED"
    assert payload["context"] == "style.backtest-rank"
    assert payload["trace_id"]
    assert payload["details"]["strict_mode"] is True
    assert payload["details"]["completed_styles"] == []

    with get_session() as session:
        rows = session.exec(select(SystemLog)).all()
    assert len(rows) == 1
    assert rows[0].error_code == "E_STYLE_EVAL_FAILED"
    assert rows[0].context == "style.backtest-rank"


def _seed_market_and_positions(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "signal-ok.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables()

    start = datetime(2025, 10, 1, tzinfo=timezone.utc)
    with get_session() as session:
        for i in range(120):
            ts = start + timedelta(days=i)
            # BTC：震荡上行
            btc_close = 100 + i * 0.8 + (i % 7) * 0.3
            # ETH：缓慢上行
            eth_close = 60 + i * 0.5 + (i % 5) * 0.2
            # SOL：高波动，便于风险与相关性信号计算
            sol_close = 30 + i * 0.7 + ((i % 9) - 4) * 0.6
            for symbol, close in (
                ("BTC", btc_close),
                ("ETH", eth_close),
                ("SOL", sol_close),
            ):
                session.add(
                    MarketBar(
                        symbol=symbol,
                        timestamp=ts,
                        open=close * 0.995,
                        high=close * 1.01,
                        low=close * 0.99,
                        close=close,
                        volume=1000.0 + i * 3,
                    )
                )

        session.add(Position(symbol="BTC", quantity=0.5, market_value=800.0, weight=0.5))
        session.add(Position(symbol="ETH", quantity=2.0, market_value=500.0, weight=0.3))
        session.add(Position(symbol="SOL", quantity=20.0, market_value=300.0, weight=0.2))
        session.commit()


def test_signal_snapshot_json_success_with_seed_data(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["signal", "snapshot", "--output", "json"])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(result.stdout)
    assert "signals" in payload
    assert isinstance(payload["signals"], list)
    assert len(payload["signals"]) == 24
    assert payload["as_of"]
    assert "data_window" in payload
    assert "category_metrics" in payload
    assert "conflict_matrix" in payload
    assert payload["feature_set_version"] == "signal-v1.0"
    assert payload["style_preset_version"] == "style-v1.0"
    assert payload["symbols_hash"]
    assert payload["params_hash"]
    assert payload["code_version"]

    first = payload["signals"][0]
    assert set(
        [
            "signal_key",
            "category",
            "symbol",
            "as_of",
            "state",
            "value",
            "threshold",
            "triggered",
            "confidence",
            "explanation",
        ]
    ).issubset(first.keys())


def test_signal_trend_json_outputs_only_trend_category(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["signal", "trend", "--output", "json"])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(result.stdout)
    assert payload["category"] == "trend"
    assert len(payload["signals"]) == 6
    assert all(item["category"] == "trend" for item in payload["signals"])
    assert all(item["signal_key"] in {
        "golden_cross",
        "death_cross",
        "breakout_20d",
        "breakdown_20d",
        "momentum_20d",
        "macd_cross",
    } for item in payload["signals"])
    assert all(item["state"] in {"bullish", "neutral", "bearish"} for item in payload["signals"])


def test_style_backtest_rank_json_success_with_seed_data(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["style", "backtest-rank", "--output", "json"])
    assert result.exit_code == 0, result.stdout

    payload = json.loads(result.stdout)
    assert payload["sort_key"] == "calmar"
    assert "rank_table" in payload
    assert len(payload["rank_table"]) == 4
    assert "styles" in payload
    assert len(payload["styles"]) == 4
    assert "recommended_style" not in payload
    assert payload["feature_set_version"] == "signal-v1.0"
    assert payload["style_preset_version"] == "style-v1.0"
    assert payload["symbols_hash"]
    assert payload["params_hash"]
    assert payload["code_version"]
    assert payload["objective"] == "calmar"
    assert payload["search_method"] == "grid_search"
    assert payload["constraints"]["mdd_floor"] == -0.2
    assert payload["candidates_count"] == 4
    assert payload["valid_candidates_count"] == 4
    assert payload["best_candidate"]["rank"] == 1


def test_signal_trend_pretty_table_headers_are_chinese(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["signal", "trend"])
    assert result.exit_code == 0, result.stdout
    assert "信号键" in result.stdout
    assert "状态" in result.stdout
    assert "数值" in result.stdout
    assert "触发" in result.stdout
    assert "金叉" in result.stdout
    assert any(label in result.stdout for label in ("看多", "看空", "中性"))
    assert "golden_cross" not in result.stdout


def test_style_backtest_rank_pretty_table_headers_are_chinese(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["style", "backtest-rank"])
    assert result.exit_code == 0, result.stdout
    assert "排名" in result.stdout
    assert "风格" in result.stdout
    assert "总收益" in result.stdout
    assert "最大回撤" in result.stdout
    assert "夏普" in result.stdout
    assert "卡玛" in result.stdout


def test_signal_snapshot_history_and_show_json(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    snapshot_result = runner.invoke(app, ["signal", "snapshot", "--output", "json"])
    assert snapshot_result.exit_code == 0, snapshot_result.stdout

    history_result = runner.invoke(app, ["signal", "history", "--output", "json"])
    assert history_result.exit_code == 0, history_result.stdout
    rows = json.loads(history_result.stdout)
    assert isinstance(rows, list)
    assert len(rows) >= 1
    assert "id" in rows[0]
    assert "snapshot_id" in rows[0]
    assert "signals_count" in rows[0]
    assert rows[0]["signals_count"] == 24

    show_result = runner.invoke(app, ["signal", "show", str(rows[0]["id"]), "--output", "json"])
    assert show_result.exit_code == 0, show_result.stdout
    show_payload = json.loads(show_result.stdout)
    assert len(show_payload["signals"]) == 24
    assert show_payload["snapshot_id"] == rows[0]["snapshot_id"]
    assert show_payload["feature_set_version"] == "signal-v1.0"
    assert show_payload["style_preset_version"] == "style-v1.0"
    assert show_payload["symbols_hash"]
    assert show_payload["params_hash"]
    assert show_payload["code_version"]


def test_style_backtest_rank_history_and_show_json(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    rank_result = runner.invoke(app, ["style", "backtest-rank", "--output", "json"])
    assert rank_result.exit_code == 0, rank_result.stdout

    history_result = runner.invoke(app, ["style", "history", "--output", "json"])
    assert history_result.exit_code == 0, history_result.stdout
    rows = json.loads(history_result.stdout)
    assert isinstance(rows, list)
    assert len(rows) >= 1
    assert "id" in rows[0]
    assert "run_id" in rows[0]
    assert "styles_count" in rows[0]
    assert rows[0]["styles_count"] == 4

    show_result = runner.invoke(app, ["style", "show", str(rows[0]["id"]), "--output", "json"])
    assert show_result.exit_code == 0, show_result.stdout
    show_payload = json.loads(show_result.stdout)
    assert len(show_payload["styles"]) == 4
    assert len(show_payload["rank_table"]) == 4
    assert show_payload["run_id"] == rows[0]["run_id"]
    assert show_payload["feature_set_version"] == "signal-v1.0"
    assert show_payload["style_preset_version"] == "style-v1.0"
    assert show_payload["symbols_hash"]
    assert show_payload["params_hash"]
    assert show_payload["code_version"]
    assert show_payload["objective"] == "calmar"
    assert show_payload["search_method"] == "grid_search"
    assert show_payload["constraints"]["mdd_floor"] == -0.2
    assert show_payload["candidates_count"] == 4
    assert show_payload["valid_candidates_count"] == 4
    assert show_payload["best_candidate"]["rank"] == 1
