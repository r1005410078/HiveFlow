# tests/test_cli_sync.py
import json
from datetime import datetime, timezone
from unittest.mock import patch

from typer.testing import CliRunner

from hiveflow.application.sync import SyncResult
from hiveflow.cli import app
from hiveflow.infrastructure.okx.okx_provider import OkxAuthError


def _result(positions=3, prices=3, candles=0) -> SyncResult:
    return SyncResult(
        synced_at=datetime(2026, 3, 16, 9, 32, tzinfo=timezone.utc),
        positions_synced=positions, prices_synced=prices,
        candles_synced=candles, total_value_usdt=12450.0,
    )


def test_sync_command_help() -> None:
    assert CliRunner().invoke(app, ["sync", "--help"]).exit_code == 0


def test_sync_outputs_summary(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.sync_from_okx", return_value=_result()):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "同步完成" in result.output


def test_sync_json_output(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.sync_from_okx", return_value=_result()):
        result = CliRunner().invoke(app, ["sync", "--output", "json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["positions_synced"] == 3


def test_sync_fails_without_api_key() -> None:
    result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "OKX_API_KEY" in result.output


def test_sync_days_flag_passed_to_usecase(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.sync_from_okx", return_value=_result(candles=70)) as mock_fn:
        CliRunner().invoke(app, ["sync", "--days", "7"])
    assert mock_fn.call_args.kwargs.get("days") == 7


def test_sync_rejects_days_over_100(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    result = CliRunner().invoke(app, ["sync", "--days", "200"])
    assert result.exit_code == 1
    assert "100" in result.output


def test_sync_shows_auth_error(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "bad")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "bad")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "bad")
    with patch("hiveflow.cli.sync_from_okx", side_effect=OkxAuthError("鉴权失败")):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "鉴权失败" in result.output
