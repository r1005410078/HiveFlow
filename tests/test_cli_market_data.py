import json
from pathlib import Path

from typer.testing import CliRunner

from hiveflow.cli import app


def test_market_data_command_group_is_available() -> None:
    result = CliRunner().invoke(app, ["market-data", "--help"])
    assert result.exit_code == 0


def test_market_data_template_supports_json_output(tmp_path: Path) -> None:
    file = tmp_path / "prices.csv"
    result = CliRunner().invoke(
        app, ["market-data", "template", "--file", str(file), "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(file)
    assert payload["rows"] == 4


def test_market_data_validate_reports_result(tmp_path: Path) -> None:
    file = tmp_path / "prices.csv"
    file.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T00:00:00Z,100,110,95,105,1000\n"
        ),
        encoding="utf-8",
    )
    result = CliRunner().invoke(
        app, ["market-data", "validate", "--file", str(file), "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["valid"] is True
    assert payload["rows"] == 1


def test_market_data_import_list_summary_support_json(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "market-cli.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    file = tmp_path / "prices.csv"
    file.write_text(
        (
            "symbol,timestamp,open,high,low,close,volume\n"
            "BTC,2026-03-13T00:00:00Z,100,110,95,105,1000\n"
            "BTC,2026-03-13T01:00:00Z,105,112,101,111,1200\n"
            "ETH,2026-03-13T00:00:00Z,50,55,45,50,2000\n"
        ),
        encoding="utf-8",
    )
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["market-data", "import", "--file", str(file), "--mode", "replace", "--output", "json"],
    )
    assert import_result.exit_code == 0
    import_payload = json.loads(import_result.stdout)
    assert import_payload["imported"] == 3

    list_result = runner.invoke(
        app,
        ["market-data", "list", "--symbol", "BTC", "--output", "json"],
    )
    assert list_result.exit_code == 0
    list_payload = json.loads(list_result.stdout)
    assert len(list_payload) == 2

    summary_result = runner.invoke(app, ["market-data", "summary", "--output", "json"])
    assert summary_result.exit_code == 0
    summary_payload = json.loads(summary_result.stdout)
    assert summary_payload["symbols_count"] == 2
    assert summary_payload["bars_count"] == 3
