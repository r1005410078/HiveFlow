import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlmodel import select
from typer.testing import CliRunner

from hiveflow.cli import app
from hiveflow.db import get_session
from hiveflow.db import create_all_tables
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.domain.signal_snapshots import SignalSnapshot
from hiveflow.domain.style_backtest_results import StyleBacktestResult
from hiveflow.domain.system_logs import SystemLog
from hiveflow.application.style_backtest import StyleBacktestError


def test_signal_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["signal", "--help"])
    assert result.exit_code == 0


def test_style_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["style", "--help"])
    assert result.exit_code == 0


def test_context_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["context", "--help"])
    assert result.exit_code == 0


def test_context_daily_json_strict_failure_when_missing_signal_history(
    tmp_path, monkeypatch
) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    result = runner.invoke(app, ["context", "daily", "--output", "json"])
    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["code"] == "E_SIGNAL_REQUIRED_MISSING"
    assert payload["context"] == "context.daily"
    assert payload["details"]["strict_mode"] is True


def test_context_daily_json_success_with_latest_snapshots(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()

    signal_result = runner.invoke(app, ["signal", "snapshot", "--output", "json"])
    assert signal_result.exit_code == 0, signal_result.stdout
    style_result = runner.invoke(app, ["style", "backtest-rank", "--output", "json"])
    assert style_result.exit_code == 0, style_result.stdout

    result = runner.invoke(app, ["context", "daily", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)

    assert "as_of" in payload
    assert "check" in payload
    assert "drift" in payload
    assert "source_meta" in payload
    assert "signal_latest" in payload
    assert "style_latest" in payload
    assert payload["decision_boundary"]["system"] == "data_only"
    assert payload["decision_boundary"]["agent"] == "analysis_and_decision"
    assert payload["check"]["verdict"] in {"safe", "watch", "danger"}
    assert isinstance(payload["drift"]["items"], list)
    assert len(payload["signal_latest"]["signals"]) == 24
    assert len(payload["style_latest"]["rank_table"]) == 4
    assert payload["signal_latest"]["feature_set_version"] == "signal-v1.0"
    assert payload["style_latest"]["objective"] == "calmar"
    assert payload["source_meta"]["strict_source"] == "latest"
    assert payload["source_meta"]["max_age_hours"] == 24
    assert payload["source_meta"]["signal_latest"]["record_id"] >= 1
    assert payload["source_meta"]["style_latest"]["record_id"] >= 1
    assert payload["source_meta"]["signal_latest"]["age_hours"] >= 0
    assert payload["source_meta"]["style_latest"]["age_hours"] >= 0
    assert "windows" in payload
    assert set(payload["windows"].keys()) == {"w24", "w7", "w30"}
    assert payload["windows"]["w24"]["window_size"] == 24
    assert payload["windows"]["w7"]["window_size"] == 7
    assert payload["windows"]["w30"]["window_size"] == 30
    for key in ("w24", "w7", "w30"):
        row = payload["windows"][key]
        assert "check" in row
        assert "drift" in row
        assert "signal" in row
        assert "style" in row
        assert "source_meta" in row
        assert len(row["signal"]["signals"]) == 24
        assert len(row["style"]["rank_table"]) == 4
    run_ids = {
        payload["windows"]["w24"]["style"]["run_id"],
        payload["windows"]["w7"]["style"]["run_id"],
        payload["windows"]["w30"]["style"]["run_id"],
    }
    assert len(run_ids) == 3
    assert "window_diff" in payload
    assert "signal_diff" in payload["window_diff"]
    assert "style_diff" in payload["window_diff"]
    assert "risk_diff" in payload["window_diff"]
    assert "consensus_score" in payload["window_diff"]
    assert 0.0 <= payload["window_diff"]["consensus_score"] <= 1.0


def test_context_daily_supports_json_schema() -> None:
    result = CliRunner().invoke(app, ["context", "daily", "--json-schema"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["title"] == "HiveFlow context.daily output envelope"
    assert "data" in payload["properties"]


def test_context_daily_json_supports_envelope(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    result = runner.invoke(app, ["context", "daily", "--output", "json", "--envelope"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "context.daily"
    assert "data" in payload
    assert "source_meta" in payload["data"]
    assert "signal_latest" in payload["data"]
    assert "style_latest" in payload["data"]


def test_context_daily_fresh_fails_when_latest_snapshot_is_stale(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    stale_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    with get_session() as session:
        sig = session.exec(select(SignalSnapshot)).first()
        sty = session.exec(select(StyleBacktestResult)).first()
        assert sig is not None
        assert sty is not None
        sig.as_of = stale_at
        sty.as_of = stale_at
        session.add(sig)
        session.add(sty)
        session.commit()

    result = runner.invoke(
        app,
        [
            "context",
            "daily",
            "--output",
            "json",
            "--strict-source",
            "fresh",
            "--max-age-hours",
            "24",
        ],
    )
    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["code"] == "E_PIPELINE_ABORTED_STRICT"
    assert payload["context"] == "context.daily"
    assert payload["details"]["strict_mode"] is True
    assert "stale_components" in payload["details"]
    assert payload["details"]["stale_components"]


def test_context_daily_fresh_succeeds_with_relaxed_max_age(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    result = runner.invoke(
        app,
        [
            "context",
            "daily",
            "--output",
            "json",
            "--strict-source",
            "fresh",
            "--max-age-hours",
            "5000",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["source_meta"]["strict_source"] == "fresh"
    assert payload["source_meta"]["max_age_hours"] == 5000
    assert "signal_latest" in payload
    assert "style_latest" in payload


def test_context_daily_strict_window_partial_returns_success_with_failures(
    tmp_path, monkeypatch
) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    original = __import__("hiveflow.cli", fromlist=["run_style_backtest_rank"]).run_style_backtest_rank

    def _patched_style(*, settings=None, rebalance_days=7, symbols=None, window_bars=None, fee_bps=0.0, slippage_bps=0.0):
        if window_bars == 7:
            raise StyleBacktestError(
                context="style.backtest-rank",
                message="mocked window failure",
                details={"strict_mode": True, "failed_style": "w7"},
                hint={"action": "mock"},
            )
        return original(
            settings=settings,
            rebalance_days=rebalance_days,
            symbols=symbols,
            window_bars=window_bars,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )

    with patch("hiveflow.cli.run_style_backtest_rank", side_effect=_patched_style):
        result = runner.invoke(
            app,
            ["context", "daily", "--output", "json", "--strict-window", "partial"],
        )

    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["summary"]["window_count_failed"] == 1
    assert payload["summary"]["window_count_success"] == 2
    assert payload["summary"]["window_count_total_computed"] == 3
    assert payload["summary"]["window_count_total_computed"] == payload["summary"]["window_count_requested"]
    assert payload["summary"]["is_window_audit_consistent"] is True
    assert payload["summary"]["window_audit"]["window_count_requested"] == 3
    assert payload["summary"]["window_audit"]["window_count_total_computed"] == 3
    assert payload["summary"]["window_audit"]["is_window_audit_consistent"] is True
    assert payload["summary"]["window_audit"]["window_audit_schema_version"] == "v1"
    assert payload["summary"]["window_keys_success"] == ["w24", "w30"]
    assert payload["summary"]["window_keys_failed"] == ["w7"]
    assert payload["summary"]["window_status_map"] == {
        "w24": "ok",
        "w7": "failed",
        "w30": "ok",
    }
    assert len(payload["summary"]["window_failures"]) == 1
    assert payload["summary"]["window_failures"][0]["window_key"] == "w7"
    assert payload["windows"]["w7"]["status"] == "failed"


def test_context_daily_strict_window_all_fails_when_any_window_failed(
    tmp_path, monkeypatch
) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    original = __import__("hiveflow.cli", fromlist=["run_style_backtest_rank"]).run_style_backtest_rank

    def _patched_style(*, settings=None, rebalance_days=7, symbols=None, window_bars=None, fee_bps=0.0, slippage_bps=0.0):
        if window_bars == 7:
            raise StyleBacktestError(
                context="style.backtest-rank",
                message="mocked window failure",
                details={"strict_mode": True, "failed_style": "w7"},
                hint={"action": "mock"},
            )
        return original(
            settings=settings,
            rebalance_days=rebalance_days,
            symbols=symbols,
            window_bars=window_bars,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )

    with patch("hiveflow.cli.run_style_backtest_rank", side_effect=_patched_style):
        result = runner.invoke(
            app,
            ["context", "daily", "--output", "json", "--strict-window", "all"],
        )

    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert payload["code"] == "E_PIPELINE_ABORTED_STRICT"
    assert payload["context"] == "context.daily"
    assert payload["details"]["strict_window"] == "all"
    assert payload["details"]["window_count_success"] == 2
    assert payload["details"]["window_count_failed"] == 1
    assert payload["details"]["window_count_total_computed"] == 3
    assert payload["details"]["window_count_total_computed"] == payload["details"]["window_count_requested"]
    assert payload["details"]["is_window_audit_consistent"] is True
    assert payload["details"]["window_audit"]["window_count_requested"] == 3
    assert payload["details"]["window_audit"]["window_count_total_computed"] == 3
    assert payload["details"]["window_audit"]["is_window_audit_consistent"] is True
    assert payload["details"]["window_audit"]["window_audit_schema_version"] == "v1"
    assert payload["details"]["window_keys_failed"] == ["w7"]
    assert payload["details"]["window_status_map"] == {
        "w24": "ok",
        "w7": "failed",
        "w30": "ok",
    }
    assert len(payload["details"]["window_failures"]) == 1
    assert payload["details"]["window_failures"][0]["window_key"] == "w7"


def test_context_daily_supports_custom_windows(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    runner = CliRunner()
    assert runner.invoke(app, ["signal", "snapshot", "--output", "json"]).exit_code == 0
    assert runner.invoke(app, ["style", "backtest-rank", "--output", "json"]).exit_code == 0

    result = runner.invoke(
        app,
        ["context", "daily", "--output", "json", "--windows", "12,24"],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert set(payload["windows"].keys()) == {"w12", "w24"}
    assert payload["windows"]["w12"]["window_size"] == 12
    assert payload["windows"]["w24"]["window_size"] == 24
    assert payload["summary"]["window_count_success"] == 2
    assert payload["summary"]["window_count_failed"] == 0
    assert payload["summary"]["window_count_total_computed"] == 2
    assert payload["summary"]["window_count_requested"] == 2
    assert payload["summary"]["window_count_total_computed"] == payload["summary"]["window_count_requested"]
    assert payload["summary"]["is_window_audit_consistent"] is True
    assert payload["summary"]["window_audit"]["window_count_requested"] == 2
    assert payload["summary"]["window_audit"]["window_count_total_computed"] == 2
    assert payload["summary"]["window_audit"]["is_window_audit_consistent"] is True
    assert payload["summary"]["window_audit"]["window_audit_schema_version"] == "v1"
    assert payload["summary"]["windows_requested"] == [12, 24]
    assert payload["summary"]["window_keys_success"] == ["w12", "w24"]
    assert payload["summary"]["window_keys_failed"] == []
    assert payload["summary"]["window_status_map"] == {
        "w12": "ok",
        "w24": "ok",
    }


@pytest.mark.parametrize(
    "windows",
    [
        "",
        "0,24",
        "abc,24",
        "24,,7",
    ],
)
def test_context_daily_rejects_invalid_windows_option(tmp_path, monkeypatch, windows: str) -> None:
    db_path = tmp_path / "invalid-windows.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables()
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["context", "daily", "--output", "json", "--windows", windows],
    )
    assert result.exit_code == 2


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


def test_build_signal_snapshot_accepts_explicit_symbol(tmp_path, monkeypatch) -> None:
    """build_signal_snapshot 应接受显式 symbol 参数。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_snapshot
    payload = build_signal_snapshot("BTC")
    assert payload["symbol"] == "BTC"
    assert len(payload["signals"]) == 24


def test_build_signal_snapshot_raises_on_unknown_symbol(tmp_path, monkeypatch) -> None:
    """build_signal_snapshot 对不存在的 symbol 应抛出 SignalPipelineError。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_snapshot, SignalPipelineError
    with pytest.raises(SignalPipelineError) as exc_info:
        build_signal_snapshot("XYZ_NOT_EXIST")
    assert exc_info.value.details.get("reason") == "symbol_not_found"
