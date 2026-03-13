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


def test_strategies_command_group_is_available() -> None:
    # 验证策略命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["strategies", "--help"])
    assert result.exit_code == 0


def test_slots_command_group_is_available() -> None:
    # 验证席位命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["slots", "--help"])
    assert result.exit_code == 0


def test_current_command_group_is_available() -> None:
    # 验证当前策略命令组已在 CLI 中暴露。
    result = CliRunner().invoke(app, ["current", "--help"])
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


def test_targets_list_supports_strategy_filter(tmp_path, monkeypatch) -> None:
    # 验证 targets list 支持按策略过滤。
    db_path = tmp_path / "targets-filter.db"
    csv_path = tmp_path / "targets-filter.csv"
    csv_path.write_text(
        (
            "strategy_name,symbol,target_weight\n"
            "进攻型默认策略,BTC,0.5\n"
            "进攻型默认策略,ETH,0.3\n"
            "防守型默认策略,USDT,0.6\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["targets", "import", "--file", str(csv_path), "--mode", "replace"])

    result = runner.invoke(
        app, ["targets", "list", "--strategy", "进攻型默认策略", "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 2
    assert all(item["strategy_name"] == "进攻型默认策略" for item in payload)
    assert all("strategy_type" in item for item in payload)
    assert all("dimension" in item for item in payload)


def test_targets_import_append_upserts_same_strategy_symbol(tmp_path, monkeypatch) -> None:
    # 验证 append 模式重复导入同策略同标的时会覆盖，不会累积重复行。
    db_path = tmp_path / "targets-upsert.db"
    csv_a = tmp_path / "targets-a.csv"
    csv_b = tmp_path / "targets-b.csv"
    csv_a.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.50\n",
        encoding="utf-8",
    )
    csv_b.write_text(
        "strategy_name,symbol,target_weight\n进攻型默认策略,BTC,0.55\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["targets", "import", "--file", str(csv_a), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(csv_b), "--mode", "append"])

    result = runner.invoke(
        app, ["targets", "list", "--strategy", "进攻型默认策略", "--output", "json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) == 1
    assert payload[0]["symbol"] == "BTC"
    assert payload[0]["target_weight"] == 0.55


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


def test_strategies_import_and_list_support_json_output(tmp_path, monkeypatch) -> None:
    # 验证策略支持 CSV 导入并可 JSON 列出。
    db_path = tmp_path / "strategies-import.db"
    csv_path = tmp_path / "strategies.csv"
    csv_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
            "防守轮动策略,防守型,低波动防守轮动,震荡市,最大回撤 8%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["strategies", "import", "--file", str(csv_path), "--output", "json"],
    )
    assert import_result.exit_code == 0
    import_payload = json.loads(import_result.stdout)
    assert import_payload["imported"] == 2

    list_result = runner.invoke(app, ["strategies", "list", "--output", "json"])
    assert list_result.exit_code == 0
    items = json.loads(list_result.stdout)
    assert len(items) == 2
    assert items[0]["name"] in {"进攻突破策略", "防守轮动策略"}


def test_strategies_support_type_and_dimension_fields(tmp_path, monkeypatch) -> None:
    # 验证策略支持“策略类型(strategy_type)”与“维度(dimension)”字段。
    db_path = tmp_path / "strategies-dimension.db"
    csv_path = tmp_path / "strategies-dimension.csv"
    csv_path.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "趋势动量策略,进攻型,趋势跟随+风控,趋势|动量,趋势市,年化 20%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(
        app,
        ["strategies", "import", "--file", str(csv_path), "--mode", "replace"],
    )
    assert import_result.exit_code == 0

    list_result = runner.invoke(app, ["strategies", "list", "--output", "json"])
    assert list_result.exit_code == 0
    items = json.loads(list_result.stdout)
    assert len(items) == 1
    assert items[0]["name"] == "趋势动量策略"
    assert items[0]["strategy_type"] == "进攻型"
    assert items[0]["dimension"] == "趋势|动量"


def test_strategies_template_supports_json_output(tmp_path) -> None:
    # 验证策略模板生成命令支持 JSON 输出。
    template_path = tmp_path / "strategies-template.csv"
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["strategies", "template", "--file", str(template_path), "--output", "json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["file"] == str(template_path)
    assert payload["rows"] == 2


def test_summary_json_includes_strategies_count_after_import(tmp_path, monkeypatch) -> None:
    # 验证导入策略后，summary 的策略数量会更新。
    db_path = tmp_path / "summary-strategies.db"
    csv_path = tmp_path / "strategies-summary.csv"
    csv_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "长期配置策略,长期型,长期资产配置,宽幅震荡,年化 12%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(csv_path)])

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["strategies_count"] == 1


def test_strategies_import_auto_records_decision_log(tmp_path, monkeypatch) -> None:
    # 验证导入策略后，会自动写入一条决策日志。
    db_path = tmp_path / "strategies-import-log.db"
    csv_path = tmp_path / "strategies-import-log.csv"
    csv_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    import_result = runner.invoke(app, ["strategies", "import", "--file", str(csv_path)])
    assert import_result.exit_code == 0

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    assert logs_result.exit_code == 0
    logs = json.loads(logs_result.stdout)
    assert len(logs) == 1
    assert logs[0]["decision_type"] == "strategies-import"
    assert "导入策略" in logs[0]["summary"]


def test_targets_generate_from_strategy_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证可根据策略自动生成目标持仓，并支持 JSON 输出。
    db_path = tmp_path / "targets-generate.db"
    strategies_path = tmp_path / "strategies-generate.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path)])

    generate_result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "进攻突破策略", "--output", "json"],
    )
    assert generate_result.exit_code == 0
    payload = json.loads(generate_result.stdout)
    assert payload["strategy"] == "进攻突破策略"
    assert payload["strategy_type"] == "进攻型"
    assert payload["generated"] == 3

    list_result = runner.invoke(app, ["targets", "list", "--output", "json"])
    assert list_result.exit_code == 0
    targets = json.loads(list_result.stdout)
    assert len(targets) == 3
    assert {item["symbol"] for item in targets} == {"BTC", "ETH", "USDT"}


def test_targets_generate_prefers_dimension_template(tmp_path, monkeypatch) -> None:
    # 验证存在匹配维度模板时，优先使用维度模板生成目标持仓。
    db_path = tmp_path / "targets-generate-dimension.db"
    strategies_path = tmp_path / "strategies-dimension-template.csv"
    strategies_path.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "趋势动量策略,进攻型,趋势跟随+动量确认,趋势|动量,趋势市,年化 20%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])

    generate_result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "趋势动量策略", "--output", "json"],
    )
    assert generate_result.exit_code == 0
    payload = json.loads(generate_result.stdout)
    assert payload["strategy_type"] == "进攻型"
    assert payload["dimension"] == "趋势|动量"
    assert payload["template_source"] == "dimension"

    list_result = runner.invoke(
        app, ["targets", "list", "--strategy", "趋势动量策略", "--output", "json"]
    )
    targets = json.loads(list_result.stdout)
    weights = {item["symbol"]: item["target_weight"] for item in targets}
    assert weights == {"BTC": 0.45, "ETH": 0.45, "USDT": 0.1}


def test_targets_generate_falls_back_to_type_template(tmp_path, monkeypatch) -> None:
    # 验证维度没有专属模板时，回退到策略类型模板。
    db_path = tmp_path / "targets-generate-fallback.db"
    strategies_path = tmp_path / "strategies-fallback.csv"
    strategies_path.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "进攻新维度策略,进攻型,新维度实验,未知维度,趋势市,年化 15%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])

    generate_result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "进攻新维度策略", "--output", "json"],
    )
    assert generate_result.exit_code == 0
    payload = json.loads(generate_result.stdout)
    assert payload["template_source"] == "type"

    list_result = runner.invoke(
        app, ["targets", "list", "--strategy", "进攻新维度策略", "--output", "json"]
    )
    targets = json.loads(list_result.stdout)
    weights = {item["symbol"]: item["target_weight"] for item in targets}
    assert weights == {"BTC": 0.5, "ETH": 0.3, "USDT": 0.2}


def test_targets_generate_supports_external_template_config(tmp_path, monkeypatch) -> None:
    # 验证可通过外部模板配置文件驱动目标持仓生成。
    db_path = tmp_path / "targets-generate-config.db"
    config_path = tmp_path / "target-templates.json"
    strategies_path = tmp_path / "strategies-config.csv"
    config_path.write_text(
        json.dumps(
            {
                "dimension_presets": {
                    "趋势|动量": {"BTC": 0.60, "ETH": 0.30, "USDT": 0.10}
                },
                "type_presets": {"进攻型": {"BTC": 0.50, "ETH": 0.30, "USDT": 0.20}},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "趋势动量策略,进攻型,趋势跟随+动量确认,趋势|动量,趋势市,年化 20%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HIVEFLOW_TARGET_TEMPLATE_FILE", str(config_path))
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])

    generate_result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "趋势动量策略", "--output", "json"],
    )
    assert generate_result.exit_code == 0
    payload = json.loads(generate_result.stdout)
    assert payload["template_source"] == "dimension"

    list_result = runner.invoke(
        app, ["targets", "list", "--strategy", "趋势动量策略", "--output", "json"]
    )
    targets = json.loads(list_result.stdout)
    weights = {item["symbol"]: item["target_weight"] for item in targets}
    assert weights == {"BTC": 0.6, "ETH": 0.3, "USDT": 0.1}


def test_targets_template_show_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证可以通过命令查看当前目标模板配置。
    db_path = tmp_path / "targets-template-show.db"
    config_path = tmp_path / "target-templates-show.json"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HIVEFLOW_TARGET_TEMPLATE_FILE", str(config_path))
    runner = CliRunner()

    result = runner.invoke(app, ["targets", "template-show", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert "type_presets" in payload
    assert "dimension_presets" in payload
    assert "file" in payload


def test_targets_template_set_updates_config_and_generate_result(tmp_path, monkeypatch) -> None:
    # 验证通过命令设置模板后，generate 会使用新模板。
    db_path = tmp_path / "targets-template-set.db"
    config_path = tmp_path / "target-templates-set.json"
    strategies_path = tmp_path / "strategies-template-set.csv"
    strategies_path.write_text(
        (
            "name,strategy_type,thesis,dimension,market_regime,backtest_summary\n"
            "趋势动量策略,进攻型,趋势跟随+动量确认,趋势|动量,趋势市,年化 20%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HIVEFLOW_TARGET_TEMPLATE_FILE", str(config_path))
    runner = CliRunner()

    set_result = runner.invoke(
        app,
        [
            "targets",
            "template-set",
            "--scope",
            "dimension",
            "--key",
            "趋势|动量",
            "--weights",
            "BTC=0.70,ETH=0.20,USDT=0.10",
            "--output",
            "json",
        ],
    )
    assert set_result.exit_code == 0
    set_payload = json.loads(set_result.stdout)
    assert set_payload["scope"] == "dimension"
    assert set_payload["key"] == "趋势|动量"

    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "generate", "--strategy", "趋势动量策略"])

    list_result = runner.invoke(
        app, ["targets", "list", "--strategy", "趋势动量策略", "--output", "json"]
    )
    targets = json.loads(list_result.stdout)
    weights = {item["symbol"]: item["target_weight"] for item in targets}
    assert weights == {"BTC": 0.7, "ETH": 0.2, "USDT": 0.1}

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    logs = json.loads(logs_result.stdout)
    assert any(item["decision_type"] == "targets-template-set" for item in logs)


def test_targets_generate_auto_records_decision_log(tmp_path, monkeypatch) -> None:
    # 验证自动生成目标持仓后，会自动写入决策日志。
    db_path = tmp_path / "targets-generate-log.db"
    strategies_path = tmp_path / "strategies-generate-log.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "防守轮动策略,防守型,低波动防守轮动,震荡市,最大回撤 8%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path)])

    generate_result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "防守轮动策略"],
    )
    assert generate_result.exit_code == 0

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    logs = json.loads(logs_result.stdout)
    assert any(item["decision_type"] == "targets-generate" for item in logs)


def test_targets_generate_rejects_unknown_strategy(tmp_path, monkeypatch) -> None:
    # 验证当策略不存在时，生成命令会报错。
    db_path = tmp_path / "targets-generate-unknown.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["targets", "generate", "--strategy", "不存在的策略"],
    )
    assert result.exit_code != 0
    assert "策略不存在" in (result.stdout + result.stderr)


def test_slots_list_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证席位列表支持 JSON 输出。
    db_path = tmp_path / "slots-list.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(app, ["slots", "list", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert len(payload) >= 3
    names = {item["name"] for item in payload}
    assert {"进攻席位", "防守席位", "长期席位"}.issubset(names)


def test_slots_set_weight_updates_slot_and_records_log(tmp_path, monkeypatch) -> None:
    # 验证席位权重可更新，并自动写入决策日志。
    db_path = tmp_path / "slots-set-weight.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    update_result = runner.invoke(
        app,
        ["slots", "set-weight", "--name", "进攻席位", "--weight", "0.55", "--output", "json"],
    )
    assert update_result.exit_code == 0
    payload = json.loads(update_result.stdout)
    assert payload["name"] == "进攻席位"
    assert payload["weight"] == 0.55

    list_result = runner.invoke(app, ["slots", "list", "--output", "json"])
    slots = json.loads(list_result.stdout)
    attack_slot = next(item for item in slots if item["name"] == "进攻席位")
    assert attack_slot["weight"] == 0.55

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    logs = json.loads(logs_result.stdout)
    assert any(item["decision_type"] == "slots-set-weight" for item in logs)


def test_summary_json_includes_slot_metrics(tmp_path, monkeypatch) -> None:
    # 验证 summary 返回席位统计信息。
    db_path = tmp_path / "summary-slots.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["slots", "set-weight", "--name", "防守席位", "--weight", "0.45"])

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["slots_count"] >= 3
    assert payload["enabled_slots_count"] >= 3


def test_current_strategy_set_and_show_support_json_output(tmp_path, monkeypatch) -> None:
    # 验证可设置并读取当前策略（JSON 输出）。
    db_path = tmp_path / "current-strategy.db"
    strategies_path = tmp_path / "current-strategy.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])

    set_result = runner.invoke(
        app,
        ["current", "set-strategy", "--name", "进攻突破策略", "--output", "json"],
    )
    assert set_result.exit_code == 0
    set_payload = json.loads(set_result.stdout)
    assert set_payload["current_strategy"] == "进攻突破策略"

    show_result = runner.invoke(app, ["current", "show", "--output", "json"])
    assert show_result.exit_code == 0
    show_payload = json.loads(show_result.stdout)
    assert show_payload["current_strategy"] == "进攻突破策略"


def test_current_strategy_set_rejects_unknown_strategy(tmp_path, monkeypatch) -> None:
    # 验证设置不存在的策略会报错。
    db_path = tmp_path / "current-strategy-unknown.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["current", "set-strategy", "--name", "不存在策略"],
    )
    assert result.exit_code != 0
    assert "策略不存在" in (result.stdout + result.stderr)


def test_summary_json_includes_current_strategy(tmp_path, monkeypatch) -> None:
    # 验证 summary JSON 包含当前策略。
    db_path = tmp_path / "summary-current-strategy.db"
    strategies_path = tmp_path / "summary-current.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "防守轮动策略,防守型,低波动防守轮动,震荡市,最大回撤 8%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "防守轮动策略"])

    result = runner.invoke(app, ["summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["current_strategy"] == "防守轮动策略"


def test_current_strategy_set_auto_records_decision_log(tmp_path, monkeypatch) -> None:
    # 验证设置当前策略后会自动写入决策日志。
    db_path = tmp_path / "current-strategy-log.db"
    strategies_path = tmp_path / "current-log.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "长期配置策略,长期型,长期资产配置,宽幅震荡,年化 12%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])

    set_result = runner.invoke(app, ["current", "set-strategy", "--name", "长期配置策略"])
    assert set_result.exit_code == 0

    logs_result = runner.invoke(app, ["logs", "list", "--output", "json"])
    logs = json.loads(logs_result.stdout)
    assert any(item["decision_type"] == "current-strategy-set" for item in logs)


def test_targets_generate_uses_current_strategy_when_omitted(tmp_path, monkeypatch) -> None:
    # 验证 targets generate 未传 --strategy 时会使用当前策略。
    db_path = tmp_path / "targets-generate-current.db"
    strategies_path = tmp_path / "targets-generate-current.csv"
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    generate_result = runner.invoke(app, ["targets", "generate", "--output", "json"])
    assert generate_result.exit_code == 0
    payload = json.loads(generate_result.stdout)
    assert payload["strategy"] == "进攻突破策略"
    assert payload["generated"] == 3


def test_rebalance_preview_uses_current_strategy_when_omitted(tmp_path, monkeypatch) -> None:
    # 验证 rebalance preview 未传 --strategy 时会使用当前策略。
    db_path = tmp_path / "rebalance-current.db"
    positions_path = tmp_path / "positions-current.csv"
    targets_path = tmp_path / "targets-current.csv"
    strategies_path = tmp_path / "strategies-current.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.70\nETH,2,20000,0.10\nUSDT,1,20000,0.20\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻突破策略,BTC,0.50\n进攻突破策略,ETH,0.30\n进攻突破策略,USDT,0.20\n",
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    preview_result = runner.invoke(app, ["rebalance", "preview", "--output", "json"])
    assert preview_result.exit_code == 0
    payload = json.loads(preview_result.stdout)
    assert payload["strategy"] == "进攻突破策略"
    assert payload["strategy_type"] == "进攻型"
    assert payload["dimension"] is None
    assert payload["suggestions_count"] >= 1


def test_targets_generate_requires_strategy_or_current_strategy(tmp_path, monkeypatch) -> None:
    # 验证在未传策略且未设置当前策略时，generate 会给出明确错误。
    db_path = tmp_path / "targets-generate-no-strategy.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    result = runner.invoke(app, ["targets", "generate"])
    assert result.exit_code != 0
    assert "当前策略未设置" in (result.stdout + result.stderr)


def test_positions_drift_supports_json_output(tmp_path, monkeypatch) -> None:
    # 验证 positions drift 可按当前策略输出结构化偏离结果。
    db_path = tmp_path / "positions-drift.db"
    positions_path = tmp_path / "positions-drift.csv"
    targets_path = tmp_path / "targets-drift.csv"
    strategies_path = tmp_path / "strategies-drift.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.70\nETH,2,20000,0.10\nUSDT,1,20000,0.20\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻突破策略,BTC,0.50\n进攻突破策略,ETH,0.30\n进攻突破策略,USDT,0.20\n",
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    result = runner.invoke(app, ["positions", "drift", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["strategy"] == "进攻突破策略"
    assert payload["count"] >= 3
    assert any(item["drift_level"] in {"high", "medium", "low"} for item in payload["items"])


def test_rebalance_preview_json_contains_explanation_and_risk_gate(tmp_path, monkeypatch) -> None:
    # 验证 rebalance JSON 含解释字段，且高风险买入会被门控为 hold。
    db_path = tmp_path / "rebalance-explain.db"
    positions_path = tmp_path / "positions-explain.csv"
    targets_path = tmp_path / "targets-explain.csv"
    risk_path = tmp_path / "risk-explain.csv"
    strategies_path = tmp_path / "strategies-explain.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,50000,0.50\nETH,2,10000,0.10\nUSDT,1,40000,0.40\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻突破策略,BTC,0.40\n进攻突破策略,ETH,0.40\n进攻突破策略,USDT,0.20\n",
        encoding="utf-8",
    )
    risk_path.write_text(
        "symbol,waterline,score,note\nETH,high,0.90,短期波动过高\nBTC,low,0.2,稳定\nUSDT,low,0.1,稳定\n",
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])
    runner.invoke(app, ["risk", "import", "--file", str(risk_path), "--mode", "replace"])
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    result = runner.invoke(app, ["rebalance", "preview", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    eth_item = next(item for item in payload["suggestions"] if item["symbol"] == "ETH")
    assert "explanation" in eth_item
    assert eth_item["risk_waterline"] == "high"
    assert eth_item["action"] == "hold"


def test_targets_template_rollback_restores_previous_config(tmp_path, monkeypatch) -> None:
    # 验证模板回滚可恢复到历史版本。
    db_path = tmp_path / "targets-rollback.db"
    config_path = tmp_path / "target-templates.json"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("HIVEFLOW_TARGET_TEMPLATE_FILE", str(config_path))
    runner = CliRunner()

    runner.invoke(
        app,
        [
            "targets",
            "template-set",
            "--scope",
            "dimension",
            "--key",
            "趋势|动量",
            "--weights",
            "BTC=0.70,ETH=0.20,USDT=0.10",
        ],
    )
    runner.invoke(
        app,
        [
            "targets",
            "template-set",
            "--scope",
            "dimension",
            "--key",
            "趋势|动量",
            "--weights",
            "BTC=0.50,ETH=0.30,USDT=0.20",
        ],
    )

    rollback_result = runner.invoke(
        app,
        ["targets", "template-rollback", "--output", "json"],
    )
    assert rollback_result.exit_code == 0
    rollback_payload = json.loads(rollback_result.stdout)
    assert rollback_payload["restored_version"] >= 1

    show_result = runner.invoke(app, ["targets", "template-show", "--output", "json"])
    show_payload = json.loads(show_result.stdout)
    assert show_payload["dimension_presets"]["趋势|动量"] == {
        "BTC": 0.7,
        "ETH": 0.2,
        "USDT": 0.1,
    }


def test_current_run_executes_generate_and_preview(tmp_path, monkeypatch) -> None:
    # 验证 current run 能一键串联目标生成与调仓预览。
    db_path = tmp_path / "current-run.db"
    positions_path = tmp_path / "positions-run.csv"
    strategies_path = tmp_path / "strategies-run.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,100000,0.60\nETH,2,20000,0.20\nUSDT,1,20000,0.20\n",
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    run_result = runner.invoke(app, ["current", "run", "--output", "json"])
    assert run_result.exit_code == 0
    payload = json.loads(run_result.stdout)
    assert payload["strategy"] == "进攻突破策略"
    assert payload["targets_generated"] == 3
    assert payload["suggestions_count"] >= 1


def test_doctor_and_init_demo_support_json_output(tmp_path, monkeypatch) -> None:
    # 验证 doctor 与 init-demo 命令支持 JSON 输出。
    db_path = tmp_path / "doctor-init-demo.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    init_result = runner.invoke(app, ["init-demo", "--output", "json"])
    assert init_result.exit_code == 0
    init_payload = json.loads(init_result.stdout)
    assert init_payload["positions"] >= 3
    assert init_payload["strategies"] >= 2

    doctor_result = runner.invoke(app, ["doctor", "--output", "json"])
    assert doctor_result.exit_code == 0
    doctor_payload = json.loads(doctor_result.stdout)
    assert doctor_payload["overall_status"] in {"ok", "warn"}
    assert len(doctor_payload["checks"]) >= 1


def test_json_schema_and_envelope_output(tmp_path, monkeypatch) -> None:
    # 验证统一 JSON schema 与 envelope 输出能力。
    db_path = tmp_path / "json-schema.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()

    schema_result = runner.invoke(app, ["summary", "--json-schema"])
    assert schema_result.exit_code == 0
    schema_payload = json.loads(schema_result.stdout)
    assert schema_payload["title"] == "HiveFlow summary output envelope"

    summary_result = runner.invoke(app, ["summary", "--output", "json", "--envelope"])
    assert summary_result.exit_code == 0
    envelope_payload = json.loads(summary_result.stdout)
    assert envelope_payload["schema_version"] == "1.0.0"
    assert envelope_payload["command"] == "summary"
    assert "data" in envelope_payload


def test_rebalance_table_uses_chinese_labels_and_risk_percent(tmp_path, monkeypatch) -> None:
    # 验证 Table 使用中文动作/优先级，且风险显示为百分比；JSON 保持英文枚举。
    db_path = tmp_path / "rebalance-table-zh.db"
    positions_path = tmp_path / "positions-table-zh.csv"
    targets_path = tmp_path / "targets-table-zh.csv"
    risk_path = tmp_path / "risk-table-zh.csv"
    strategies_path = tmp_path / "strategies-table-zh.csv"
    positions_path.write_text(
        "symbol,quantity,market_value,weight\nBTC,1,50000,0.50\nETH,2,10000,0.10\nUSDT,1,40000,0.40\n",
        encoding="utf-8",
    )
    targets_path.write_text(
        "strategy_name,symbol,target_weight\n进攻突破策略,BTC,0.40\n进攻突破策略,ETH,0.40\n进攻突破策略,USDT,0.20\n",
        encoding="utf-8",
    )
    risk_path.write_text(
        "symbol,waterline,score,note\nETH,high,0.90,短期波动过高\nBTC,medium,0.58,正常\nUSDT,low,0.10,稳定\n",
        encoding="utf-8",
    )
    strategies_path.write_text(
        (
            "name,category,thesis,market_regime,backtest_summary\n"
            "进攻突破策略,进攻型,顺势突破+风控,趋势市,年化 18%\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    runner = CliRunner()
    runner.invoke(app, ["positions", "import", "--file", str(positions_path), "--mode", "replace"])
    runner.invoke(app, ["targets", "import", "--file", str(targets_path), "--mode", "replace"])
    runner.invoke(app, ["risk", "import", "--file", str(risk_path), "--mode", "replace"])
    runner.invoke(app, ["strategies", "import", "--file", str(strategies_path), "--mode", "replace"])
    runner.invoke(app, ["current", "set-strategy", "--name", "进攻突破策略"])

    pretty_result = runner.invoke(
        app, ["rebalance", "preview", "--theme", "minimal"]
    )
    assert pretty_result.exit_code == 0
    assert "持有" in pretty_result.stdout
    assert "高" in pretty_result.stdout or "中" in pretty_result.stdout or "低" in pretty_result.stdout
    assert "90.00%" in pretty_result.stdout

    json_result = runner.invoke(app, ["rebalance", "preview", "--output", "json"])
    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    eth_item = next(item for item in payload["suggestions"] if item["symbol"] == "ETH")
    assert eth_item["action"] == "hold"
    assert eth_item["priority"] in {"high", "medium", "low"}


def test_command_help_includes_scene_and_example() -> None:
    # 验证核心命令帮助中包含“使用场景”和“示例（含目的说明）”。
    runner = CliRunner()
    result = runner.invoke(app, ["current", "run", "--help"])
    assert result.exit_code == 0
    assert "使用场景" in result.stdout
    assert "示例" in result.stdout
    assert "用途" in result.stdout
