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
