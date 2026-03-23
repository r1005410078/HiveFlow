import json

from typer.testing import CliRunner

from hiveflow.cli import app


def test_policy_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["policy", "--help"])
    assert result.exit_code == 0


def test_evaluation_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["evaluation", "--help"])
    assert result.exit_code == 0


def test_execution_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["execution", "--help"])
    assert result.exit_code == 0


def test_policy_rebalance_check_supports_json_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "policy",
            "rebalance-check",
            "--drift-max-abs",
            "0.01",
            "--risk-level",
            "medium",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["rebalance_allowed"] is False
    assert "drift_too_small" in payload["reason_codes"]


def test_policy_strategy_switch_check_supports_json_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "policy",
            "strategy-switch-check",
            "--current-strategy",
            "MomentumStrategy",
            "--candidate-strategy",
            "MeanReversionStrategy",
            "--current-score",
            "0.55",
            "--candidate-score",
            "0.62",
            "--min-advantage-score",
            "0.10",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["switch_allowed"] is False
    assert payload["switch_threshold_passed"] is False
    assert "advantage_not_enough" in payload["reason_codes"]


def test_evaluation_strategy_health_supports_json_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "evaluation",
            "strategy-health",
            "--strategy",
            "MomentumStrategy",
            "--current-market-fit",
            "low",
            "--backtest-quality-score",
            "0.35",
            "--stability-score",
            "0.31",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["strategy_health"] == "paused"
    assert payload["degradation_flag"] is True


def test_execution_plan_supports_json_output() -> None:
    result = CliRunner().invoke(
        app,
        [
            "execution",
            "plan",
            "--action",
            "BTC,sell,high,true,800",
            "--action",
            "ETH,buy,medium,false,500,risk_gate_buy_disabled",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["plan_state"] == "ready_for_confirmation"
    assert len(payload["orders"]) == 1
    assert len(payload["skipped"]) == 1

