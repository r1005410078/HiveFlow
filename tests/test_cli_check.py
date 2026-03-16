# tests/test_cli_check.py
from unittest.mock import patch
from typer.testing import CliRunner
from hiveflow.application.health_check import AlertLevel, AssetRiskSignal, HealthCheckResult
from hiveflow.cli import app


def _safe() -> HealthCheckResult:
    r = HealthCheckResult()
    r.signals = [AssetRiskSignal(symbol="BTC", max_drawdown_7d=-0.03, alert_level=AlertLevel.NORMAL, action_hint="")]
    return r


def _danger() -> HealthCheckResult:
    r = HealthCheckResult()
    r.signals = [AssetRiskSignal(symbol="ETH", max_drawdown_7d=-0.25, alert_level=AlertLevel.DANGER, action_hint="ETH 回撤超过 20%")]
    return r


def _no_history() -> HealthCheckResult:
    r = HealthCheckResult()
    r.has_no_history = True
    return r


def test_check_help() -> None:
    assert CliRunner().invoke(app, ["check", "--help"]).exit_code == 0


def test_check_safe_output(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/c.db")
    with patch("hiveflow.cli.run_health_check", return_value=_safe()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "安全" in result.output


def test_check_danger_output(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/c.db")
    with patch("hiveflow.cli.run_health_check", return_value=_danger()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0  # 始终退出码 0
    assert "危险" in result.output


def test_check_no_history_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/c.db")
    with patch("hiveflow.cli.run_health_check", return_value=_no_history()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "sync --days" in result.output
