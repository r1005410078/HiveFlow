import json

from typer.testing import CliRunner

from hiveflow.cli import app


def test_cli_module_imports() -> None:
    # 验证 CLI 应用对象可以被正常导入。
    assert app is not None


def test_cli_shows_help() -> None:
    # 验证根命令已注册，且可以正常输出帮助信息。
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "HiveFlow" in result.stdout


def test_log_command_is_available() -> None:
    # 验证决策日志命令已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["log", "--help"])
    assert result.exit_code == 0


def test_summary_command_is_available() -> None:
    # 验证 summary 命令已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["summary", "--help"])
    assert result.exit_code == 0


def test_positions_command_group_is_available() -> None:
    # 验证持仓命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["positions", "--help"])
    assert result.exit_code == 0


def test_positions_add_and_list_work_with_real_data(tmp_path, monkeypatch) -> None:
    # 验证可以写入持仓并在 list 中看到真实数据。
    db_path = tmp_path / "cli-test.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    add_result = runner.invoke(
        app,
        [
            "positions",
            "add",
            "--symbol",
            "btc",
            "--quantity",
            "1.5",
            "--market-value",
            "120000",
            "--weight",
            "0.6",
        ],
    )
    assert add_result.exit_code == 0

    list_result = runner.invoke(app, ["positions", "list"])
    assert list_result.exit_code == 0
    assert "BTC" in list_result.stdout
    assert "120000.00" in list_result.stdout


def test_summary_reads_real_database_state(tmp_path, monkeypatch) -> None:
    # 验证 summary 读取数据库真实状态，而不是 demo 文本。
    db_path = tmp_path / "summary-test.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    runner.invoke(
        app,
        [
            "positions",
            "add",
            "--symbol",
            "ETH",
            "--quantity",
            "2",
            "--market-value",
            "20000",
            "--weight",
            "0.2",
        ],
    )
    result = runner.invoke(app, ["summary"])
    assert result.exit_code == 0
    assert "- 持仓数量: 1" in result.stdout
    assert "- 持仓总市值: 20000.00" in result.stdout
    assert "demo data" not in result.stdout


def test_positions_list_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证持仓列表支持 JSON 输出，便于模型与程序读取。
    db_path = tmp_path / "positions-json.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "positions",
            "add",
            "--symbol",
            "btc",
            "--quantity",
            "1.5",
            "--market-value",
            "120000",
            "--weight",
            "0.6",
        ],
    )

    result = runner.invoke(app, ["positions", "list", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert isinstance(payload, list)
    assert payload[0]["symbol"] == "BTC"
    assert payload[0]["market_value"] == 120000.0


def test_summary_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证 summary 支持 JSON 输出，返回结构化聚合数据。
    db_path = tmp_path / "summary-json.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "positions",
            "add",
            "--symbol",
            "ETH",
            "--quantity",
            "2",
            "--market-value",
            "20000",
            "--weight",
            "0.2",
        ],
    )
    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["positions_count"] == 1
    assert payload["total_market_value"] == 20000.0
