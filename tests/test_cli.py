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


def test_risk_command_group_is_available() -> None:
    # 验证风险命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["risk", "--help"])
    assert result.exit_code == 0


def test_targets_command_group_is_available() -> None:
    # 验证目标持仓命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["targets", "--help"])
    assert result.exit_code == 0


def test_rebalance_command_group_is_available() -> None:
    # 验证调仓建议命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["rebalance", "--help"])
    assert result.exit_code == 0


def test_logs_command_group_is_available() -> None:
    # 验证决策日志命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["logs", "--help"])
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

    minimal_result = runner.invoke(app, ["positions", "list", "--theme", "minimal"])
    assert minimal_result.exit_code == 0


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

    minimal_result = runner.invoke(app, ["summary", "--theme", "minimal"])
    assert minimal_result.exit_code == 0
    assert "HiveFlow 状态摘要" in minimal_result.stdout


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
    assert payload["risk_high_count"] == 0
    assert payload["risk_medium_count"] == 0
    assert payload["risk_low_count"] == 0


def test_positions_import_from_csv_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证 CSV 导入持仓成功，并支持 JSON 结果输出。
    db_path = tmp_path / "import-json.db"
    csv_path = tmp_path / "positions.csv"
    csv_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1.5,120000,0.6\nETH,2,20000,0.2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        [
            "positions",
            "import",
            "--file",
            str(csv_path),
            "--output",
            "json",
        ],
    )
    assert import_result.exit_code == 0
    payload = json.loads(import_result.stdout)
    assert payload["imported"] == 2
    assert payload["mode"] == "append"

    list_result = runner.invoke(app, ["positions", "list", "--output", "json"])
    assert list_result.exit_code == 0
    positions = json.loads(list_result.stdout)
    assert len(positions) == 2


def test_positions_import_replace_mode_overwrites_existing_positions(
    tmp_path, monkeypatch
) -> None:
    # 验证 replace 模式会先清空旧持仓再导入新数据。
    db_path = tmp_path / "import-replace.db"
    csv_path = tmp_path / "positions-replace.csv"
    csv_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.5\n",
        encoding="utf-8",
    )
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
    import_result = runner.invoke(
        app,
        ["positions", "import", "--file", str(csv_path), "--mode", "replace"],
    )
    assert import_result.exit_code == 0

    list_result = runner.invoke(app, ["positions", "list", "--output", "json"])
    positions = json.loads(list_result.stdout)
    assert len(positions) == 1
    assert positions[0]["symbol"] == "BTC"


def test_positions_template_generates_csv_file(tmp_path) -> None:
    # 验证可以生成可导入的 CSV 模板文件。
    template_path = tmp_path / "positions-template.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["positions", "template", "--file", str(template_path)],
    )
    assert result.exit_code == 0
    assert template_path.exists()
    content = template_path.read_text(encoding="utf-8")
    assert "symbol,quantity,market_value,weight" in content
    assert "BTC,1.5,120000,0.6" in content


def test_positions_template_supports_json_output(tmp_path) -> None:
    # 验证模板生成命令支持 JSON 输出。
    template_path = tmp_path / "positions-template-json.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["positions", "template", "--file", str(template_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(template_path)
    assert payload["rows"] == 2


def test_risk_import_and_list_support_json_output(tmp_path, monkeypatch) -> None:
    # 验证风险信号支持 CSV 导入并可 JSON 列出。
    db_path = tmp_path / "risk-import.db"
    csv_path = tmp_path / "risk.csv"
    csv_path.write_text(
        "symbol,waterline,score,note\nBTC,high,0.82,波动加大\nETH,medium,0.55,震荡\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["risk", "import", "--file", str(csv_path), "--output", "json"],
    )
    assert import_result.exit_code == 0
    payload = json.loads(import_result.stdout)
    assert payload["imported"] == 2

    list_result = runner.invoke(app, ["risk", "list", "--output", "json"])
    assert list_result.exit_code == 0
    signals = json.loads(list_result.stdout)
    assert len(signals) == 2
    assert signals[0]["symbol"] in {"BTC", "ETH"}


def test_summary_json_includes_risk_distribution_after_import(tmp_path, monkeypatch) -> None:
    # 验证 summary JSON 包含风险分布统计（高/中/低）。
    db_path = tmp_path / "summary-risk.db"
    csv_path = tmp_path / "risk-summary.csv"
    csv_path.write_text(
        "symbol,waterline,score,note\nBTC,high,0.82,波动加大\nETH,medium,0.55,震荡\nXRP,low,0.21,稳定\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["risk", "import", "--file", str(csv_path)])

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["risk_signals_count"] == 3
    assert payload["risk_high_count"] == 1
    assert payload["risk_medium_count"] == 1
    assert payload["risk_low_count"] == 1


def test_risk_template_supports_json_output(tmp_path) -> None:
    # 验证风险模板生成命令支持 JSON 输出。
    template_path = tmp_path / "risk-template.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["risk", "template", "--file", str(template_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(template_path)
    assert payload["rows"] == 2


def test_targets_import_and_list_support_json_output(tmp_path, monkeypatch) -> None:
    # 验证目标持仓支持 CSV 导入并可 JSON 列出。
    db_path = tmp_path / "targets-import.db"
    csv_path = tmp_path / "targets.csv"
    csv_path.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.5\n进攻型默认策略,ETH,0.3\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["targets", "import", "--file", str(csv_path), "--output", "json"],
    )
    assert import_result.exit_code == 0
    payload = json.loads(import_result.stdout)
    assert payload["imported"] == 2

    list_result = runner.invoke(app, ["targets", "list", "--output", "json"])
    assert list_result.exit_code == 0
    targets = json.loads(list_result.stdout)
    assert len(targets) == 2
    assert targets[0]["strategy_name"] == "进攻型默认策略"


def test_summary_json_includes_target_count_after_import(tmp_path, monkeypatch) -> None:
    # 验证导入目标持仓后，summary 的目标数量会更新。
    db_path = tmp_path / "summary-targets.db"
    csv_path = tmp_path / "targets-summary.csv"
    csv_path.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.5\n防守型默认策略,USDT,0.4\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["targets", "import", "--file", str(csv_path)])

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["target_allocations_count"] == 2


def test_targets_template_supports_json_output(tmp_path) -> None:
    # 验证目标持仓模板生成命令支持 JSON 输出。
    template_path = tmp_path / "targets-template.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["targets", "template", "--file", str(template_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(template_path)
    assert payload["rows"] == 3


def test_rebalance_preview_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证调仓预览支持 JSON 输出。
    db_path = tmp_path / "rebalance-preview.db"
    positions_path = tmp_path / "positions.csv"
    targets_path = tmp_path / "targets.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.60\nETH,2,20000,0.20\nUSDT,1,20000,0.20\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.50\n进攻型默认策略,ETH,0.30\n进攻型默认策略,USDT,0.20\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])

    result = runner.invoke(
        app,
        ["rebalance", "preview", "--strategy", "进攻型默认策略", "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "进攻型默认策略"
    assert payload["suggestions_count"] >= 1


def test_rebalance_preview_save_updates_summary_suggestion_count(tmp_path, monkeypatch) -> None:
    # 验证 --save 会把调仓建议写入数据库，并反映到 summary。
    db_path = tmp_path / "rebalance-save.db"
    positions_path = tmp_path / "positions-save.csv"
    targets_path = tmp_path / "targets-save.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.70\nETH,2,20000,0.10\nUSDT,1,20000,0.20\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.50\n进攻型默认策略,ETH,0.30\n进攻型默认策略,USDT,0.20\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])

    preview_result = runner.invoke(
        app,
        ["rebalance", "preview", "--strategy", "进攻型默认策略", "--save"],
    )
    assert preview_result.exit_code == 0

    summary_result = runner.invoke(app, ["summary", "--output", "json"])
    payload = json.loads(summary_result.stdout)
    assert payload["rebalance_suggestions_count"] >= 1


def test_logs_list_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证决策日志支持 JSON 列表输出。
    db_path = tmp_path / "logs-list.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "log",
            "--summary",
            "减仓 BTC 10%",
            "--decision-type",
            "rebalance",
            "--notes",
            "风险水位升高",
        ],
    )

    result = runner.invoke(app, ["logs", "list", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["decision_type"] == "rebalance"
    assert payload[0]["summary"] == "减仓 BTC 10%"


def test_logs_export_generates_csv_file(tmp_path, monkeypatch) -> None:
    # 验证决策日志可以导出为 CSV 文件。
    db_path = tmp_path / "logs-export.db"
    export_path = tmp_path / "decision-logs.csv"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "log",
            "--summary",
            "保持仓位",
            "--decision-type",
            "hold",
        ],
    )

    export_result = runner.invoke(
        app,
        ["logs", "export", "--file", str(export_path), "--output", "json"],
    )
    assert export_result.exit_code == 0
    payload = json.loads(export_result.stdout)
    assert payload["rows"] == 1
    assert payload["file"] == str(export_path)
    assert export_path.exists()
    content = export_path.read_text(encoding="utf-8")
    assert "id,summary,decision_type,notes,created_at" in content
    assert "保持仓位" in content


def test_summary_json_includes_decision_logs_count(tmp_path, monkeypatch) -> None:
    # 验证 summary JSON 会返回决策日志数量。
    db_path = tmp_path / "summary-logs.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "log",
            "--summary",
            "加仓 ETH",
            "--decision-type",
            "rebalance",
        ],
    )
    runner.invoke(
        app,
        [
            "log",
            "--summary",
            "降低仓位波动",
            "--decision-type",
            "risk-control",
        ],
    )

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["decision_logs_count"] == 2


def test_targets_import_auto_records_decision_log(tmp_path, monkeypatch) -> None:
    # 验证导入目标持仓后，会自动写入一条决策日志。
    db_path = tmp_path / "targets-import-log.db"
    csv_path = tmp_path / "targets-import-log.csv"
    csv_path.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.5\n进攻型默认策略,ETH,0.3\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["targets", "import", "--file", str(csv_path), "--mode", "replace"],
    )
    assert import_result.exit_code == 0

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    assert logs_result.exit_code == 0
    logs = json.loads(logs_result.stdout)
    assert len(logs) == 1
    assert logs[0]["decision_type"] == "targets-import"
    assert "导入目标持仓" in logs[0]["summary"]
