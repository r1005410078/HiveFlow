import json
from pathlib import Path
from typing import Any

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hiveflow.application.decision_logs import export_decision_logs
from hiveflow.application.decision_logs import list_decision_logs
from hiveflow.application.decision_logs import record_decision_log
from hiveflow.application.current import set_current_strategy
from hiveflow.application.current import show_current_strategy
from hiveflow.application.backtest import list_backtest_results
from hiveflow.application.backtest import run_backtest_for_strategy
from hiveflow.application.market_data import export_market_data_template
from hiveflow.application.market_data import import_market_data_csv
from hiveflow.application.market_data import list_market_bars
from hiveflow.application.market_data import summarize_market_data
from hiveflow.application.market_data import validate_market_data_csv
from hiveflow.application.positions import add_position
from hiveflow.application.positions import analyze_positions_drift
from hiveflow.application.positions import export_positions_template
from hiveflow.application.positions import import_positions_from_csv
from hiveflow.application.positions import list_positions
from hiveflow.application.rebalance import preview_rebalance
from hiveflow.application.risk import export_risk_template
from hiveflow.application.risk import import_risk_signals_from_csv
from hiveflow.application.risk import list_risk_signals
from hiveflow.application.strategies import export_strategy_template
from hiveflow.application.strategies import import_strategies_from_csv
from hiveflow.application.strategies import list_strategies
from hiveflow.application.slots import list_slots
from hiveflow.application.slots import set_slot_weight
from hiveflow.application.summary import get_summary_stats
from hiveflow.application.targets import export_target_template
from hiveflow.application.targets import generate_targets_for_strategy
from hiveflow.application.targets import get_target_template_config
from hiveflow.application.targets import import_target_allocations_from_csv
from hiveflow.application.targets import list_target_allocations
from hiveflow.application.targets import rollback_target_template
from hiveflow.application.targets import set_target_template_preset
from hiveflow.application.system import init_demo_data
from hiveflow.application.system import run_doctor
from hiveflow.services.bootstrap import bootstrap_all
from hiveflow.application.sync import SyncResult, sync_from_okx
from hiveflow.application.health_check import AlertLevel, HealthCheckResult, run_health_check
from hiveflow.db import create_all_tables, get_session
from sqlmodel import select
from hiveflow.config import Settings
from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError, OkxProvider, OkxRateLimitError, OkxTimeoutError,
)

app = typer.Typer(help="HiveFlow 本地资产决策系统。")
positions_app = typer.Typer(help="持仓管理命令。")
risk_app = typer.Typer(help="风险信号管理命令。")
targets_app = typer.Typer(help="目标持仓管理命令。")
rebalance_app = typer.Typer(help="调仓建议命令。")
logs_app = typer.Typer(help="决策日志命令。")
strategies_app = typer.Typer(help="策略管理命令。")
slots_app = typer.Typer(help="席位管理命令。")
current_app = typer.Typer(help="当前策略命令。")
market_data_app = typer.Typer(help="行情数据契约命令。")
backtest_app = typer.Typer(help="策略回测命令。")
console = Console()
JSON_SCHEMA_VERSION = "1.0.0"


def _level_style(count: int, medium_threshold: int = 1, high_threshold: int = 5) -> str:
    """根据数量返回颜色等级样式。"""
    if count >= high_threshold:
        return "bold red"
    if count >= medium_threshold:
        return "bold yellow"
    return "bold green"


def _validate_output_format(value: str) -> str:
    """校验输出格式参数。"""
    normalized = value.strip().lower()
    if normalized not in {"pretty", "json"}:
        raise typer.BadParameter("输出格式仅支持 pretty 或 json。")
    return normalized


def _validate_import_mode(value: str) -> str:
    """校验导入模式参数。"""
    normalized = value.strip().lower()
    if normalized not in {"append", "replace"}:
        raise typer.BadParameter("导入模式仅支持 append 或 replace。")
    return normalized


def _validate_theme(value: str) -> str:
    """校验显示主题参数。"""
    normalized = value.strip().lower()
    if normalized not in {"hacker", "minimal"}:
        raise typer.BadParameter("主题仅支持 hacker 或 minimal。")
    return normalized


def _validate_limit(value: int) -> int:
    """校验列表和导出的条数上限。"""
    if value <= 0:
        raise typer.BadParameter("limit 必须大于 0。")
    return value


def _action_label(action: str) -> str:
    """动作枚举中文显示。"""
    return {"buy": "买入", "sell": "卖出", "hold": "持有"}.get(action, action)


def _priority_label(priority: str) -> str:
    """优先级枚举中文显示。"""
    return {"high": "高", "medium": "中", "low": "低"}.get(priority, priority)


def _drift_level_label(level: str) -> str:
    """偏离等级枚举中文显示。"""
    return {"high": "高", "medium": "中", "low": "低"}.get(level, level)


def _build_json_envelope(command: str, data: Any) -> dict[str, Any]:
    """构建统一 JSON 包装层，供 AI/Skills 稳定消费。"""
    return {
        "schema_version": JSON_SCHEMA_VERSION,
        "command": command,
        "data": data,
    }


def _print_json(payload: Any, command: str, envelope: bool) -> None:
    """输出 JSON，可选包一层统一 envelope。"""
    body: Any = _build_json_envelope(command=command, data=payload) if envelope else payload
    typer.echo(json.dumps(body, ensure_ascii=False, indent=2))


def _print_json_schema(command: str) -> None:
    """输出统一 JSON envelope 的通用 schema。"""
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"HiveFlow {command} output envelope",
        "type": "object",
        "required": ["schema_version", "command", "data"],
        "properties": {
            "schema_version": {"type": "string", "const": JSON_SCHEMA_VERSION},
            "command": {"type": "string"},
            "data": {},
        },
    }
    typer.echo(json.dumps(schema, ensure_ascii=False, indent=2))


def _parse_weights(text: str) -> dict[str, float]:
    """解析权重参数，格式：BTC=0.5,ETH=0.3,USDT=0.2。"""
    result: dict[str, float] = {}
    for part in text.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise typer.BadParameter("weights 格式错误，需为 SYMBOL=WEIGHT。")
        symbol, value = item.split("=", 1)
        symbol = symbol.strip().upper()
        if not symbol:
            raise typer.BadParameter("weights 中 symbol 不能为空。")
        try:
            result[symbol] = float(value.strip())
        except ValueError as exc:
            raise typer.BadParameter("weights 中 weight 必须是数字。") from exc
    if not result:
        raise typer.BadParameter("weights 不能为空。")
    return result


@app.callback()
def main() -> None:
    """HiveFlow CLI 主入口。"""


@app.command("bootstrap")
def bootstrap_command() -> None:
    """初始化本地数据表并写入基础种子数据。"""
    bootstrap_all()
    typer.echo("HiveFlow bootstrap completed.")


@app.command("log")
def log_command(
    summary: str = typer.Option(..., help="决策摘要"),
    decision_type: str = typer.Option(..., help="决策类型"),
    notes: str | None = typer.Option(None, help="可选备注"),
) -> None:
    """写入一条简单的决策日志记录。"""
    record_decision_log(summary=summary, decision_type=decision_type, notes=notes)
    typer.echo("Decision log recorded.")


@app.command("doctor")
def doctor_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """检查数据库、配置与基础数据状态。

    使用场景：
    - 启动前检查环境是否健康（数据库、模板配置、基础数据）。

    示例：
    - uv run hiveflow doctor
      用途：快速体检当前环境，适合每天开工先跑一次。
    - uv run hiveflow doctor --output json
      用途：给脚本/AI 读取诊断结果并自动提醒。
    """
    if json_schema:
        _print_json_schema("doctor")
        return

    output_format = _validate_output_format(output)
    result = run_doctor()
    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="doctor", envelope=envelope)
        return

    typer.echo(f"总体状态：{result.overall_status}")
    for item in result.checks:
        typer.echo(f"- [{item.status}] {item.name}: {item.detail}")


@app.command("init-demo")
def init_demo_command(
    reset: bool = typer.Option(True, "--reset/--no-reset", help="是否先清空并重建演示数据"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """一键初始化可演示的数据样本。

    使用场景：
    - 新环境快速跑通闭环，不想手工准备 CSV。

    示例：
    - uv run hiveflow init-demo
      用途：重置并生成演示数据，5 分钟跑通全流程。
    - uv run hiveflow init-demo --no-reset
      用途：保留现有数据，仅补齐演示基线。
    - uv run hiveflow init-demo --output json
      用途：在自动化流程中拿到初始化结果。
    """
    if json_schema:
        _print_json_schema("init-demo")
        return

    output_format = _validate_output_format(output)
    result = init_demo_data(reset=reset)
    record_decision_log(
        summary="初始化演示数据",
        decision_type="init-demo",
        notes=f"positions={result.positions}, strategies={result.strategies}, targets={result.targets}",
    )

    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="init-demo", envelope=envelope)
        return
    typer.echo(
        "演示数据初始化完成："
        f"策略={result.strategies}，持仓={result.positions}，风险={result.risks}，"
        f"目标持仓={result.targets}，当前策略={result.current_strategy}"
    )


@logs_app.command("list")
def list_logs_command(
    limit: int = typer.Option(100, "--limit", help="最多返回日志条数"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """按时间倒序列出决策日志。"""
    if json_schema:
        _print_json_schema("logs.list")
        return

    row_limit = _validate_limit(limit)
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    logs = list_decision_logs(limit=row_limit)

    if not logs:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无决策日志。")
        return

    if output_format == "json":
        _print_json(
            payload=[item.to_dict() for item in logs],
            command="logs.list",
            envelope=envelope,
        )
        return

    if ui_theme == "minimal":
        table = Table(title="决策日志", show_lines=False, box=box.SIMPLE)
        table.add_column("时间", justify="left")
        table.add_column("类型", justify="left")
        table.add_column("摘要", justify="left")
        table.add_column("备注", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: DECISION LOGS ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("时间", justify="left", style="#5f875f")
        table.add_column("类型", justify="left", style="#5f875f")
        table.add_column("摘要", justify="left", style="#87ff87")
        table.add_column("备注", justify="left", style="#5f875f")

    for item in logs:
        table.add_row(
            item.created_at,
            item.decision_type,
            item.summary,
            item.notes or "-",
        )
    console.print(table)


@logs_app.command("export")
def export_logs_command(
    file: Path = typer.Option(
        Path("decision-logs.csv"),
        "--file",
        "-f",
        help="导出文件路径（默认：./decision-logs.csv）",
    ),
    limit: int = typer.Option(1000, "--limit", help="最多导出日志条数"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出决策日志为 CSV 文件。"""
    row_limit = _validate_limit(limit)
    output_format = _validate_output_format(output)
    result = export_decision_logs(file=file, limit=row_limit)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"决策日志导出完成：{result.rows} 条 -> {result.file}")


@strategies_app.command("list")
def list_strategies_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """列出当前所有策略记录。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    strategies = list_strategies()
    if not strategies:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无策略记录。")
        return

    if output_format == "json":
        payload = [item.to_dict() for item in strategies]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if ui_theme == "minimal":
        table = Table(title="策略列表", show_lines=False, box=box.SIMPLE)
        table.add_column("策略名称", justify="left")
        table.add_column("类型", justify="left")
        table.add_column("维度", justify="left")
        table.add_column("理念", justify="left")
        table.add_column("适用市场", justify="left")
        table.add_column("回测摘要", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: STRATEGIES ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("策略名称", justify="left", style="#87ff87")
        table.add_column("类型", justify="left", style="#5f875f")
        table.add_column("维度", justify="left", style="#5f875f")
        table.add_column("理念", justify="left", style="#5f875f")
        table.add_column("适用市场", justify="left", style="#5f875f")
        table.add_column("回测摘要", justify="left", style="#5f875f")

    for item in strategies:
        table.add_row(
            item.name,
            item.category,
            item.dimension or "-",
            item.thesis,
            item.market_regime or "-",
            item.backtest_summary or "-",
        )
    console.print(table)


@strategies_app.command("import")
def import_strategies_command(
    file: Path = typer.Option(..., "--file", "-f", help="CSV 文件路径"),
    mode: str = typer.Option("append", "--mode", "-m", help="导入模式：append/replace"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从 CSV 导入策略。"""
    output_format = _validate_output_format(output)
    import_mode = _validate_import_mode(mode)
    try:
        result = import_strategies_from_csv(file=file, mode=import_mode)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"导入策略 {result.imported} 条（模式：{result.mode}）",
        decision_type="strategies-import",
        notes=f"file={file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"策略导入完成：{result.imported} 条（模式：{result.mode}）。")


@strategies_app.command("template")
def export_strategies_template_command(
    file: Path = typer.Option(
        Path("strategies.csv"),
        "--file",
        "-f",
        help="模板输出路径（默认：./strategies.csv）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出策略 CSV 模板。"""
    output_format = _validate_output_format(output)
    result = export_strategy_template(file=file)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"策略模板已生成：{result.file}")


@slots_app.command("list")
def list_slots_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """列出策略席位。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    items = list_slots()

    if output_format == "json":
        typer.echo(json.dumps([item.to_dict() for item in items], ensure_ascii=False, indent=2))
        return

    if ui_theme == "minimal":
        table = Table(title="策略席位", show_lines=False, box=box.SIMPLE)
        table.add_column("席位", justify="left")
        table.add_column("用途", justify="left")
        table.add_column("类型", justify="left")
        table.add_column("权重", justify="right")
        table.add_column("启用", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: STRATEGY SLOTS ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("席位", justify="left", style="#87ff87")
        table.add_column("用途", justify="left", style="#5f875f")
        table.add_column("类型", justify="left", style="#5f875f")
        table.add_column("权重", justify="right", style="#5f875f")
        table.add_column("启用", justify="left", style="#5f875f")

    for item in items:
        table.add_row(
            item.name,
            item.purpose,
            item.allowed_category or "-",
            f"{item.weight:.2%}",
            "是" if item.enabled else "否",
        )
    console.print(table)


@slots_app.command("set-weight")
def set_slot_weight_command(
    name: str = typer.Option(..., "--name", help="席位名称"),
    weight: float = typer.Option(..., "--weight", help="席位目标权重（0~1）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """更新席位权重。"""
    output_format = _validate_output_format(output)
    try:
        result = set_slot_weight(name=name, weight=weight)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"更新席位权重：{result.name} -> {result.weight:.2%}",
        decision_type="slots-set-weight",
        notes=f"name={result.name}, weight={result.weight}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"席位权重更新成功：{result.name} -> {result.weight:.2%}")


@current_app.command("show")
def show_current_strategy_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """查看当前策略。"""
    if json_schema:
        _print_json_schema("current.show")
        return

    output_format = _validate_output_format(output)
    result = show_current_strategy()
    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="current.show", envelope=envelope)
        return
    typer.echo(f"当前策略：{result.current_strategy or '未设置'}")


@current_app.command("set-strategy")
def set_current_strategy_command(
    name: str = typer.Option(..., "--name", help="策略名称"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """设置当前策略。"""
    output_format = _validate_output_format(output)
    try:
        result = set_current_strategy(name=name)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"设置当前策略：{name}",
        decision_type="current-strategy-set",
        notes=f"strategy={name}",
    )
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"当前策略已设置为：{name}")


@current_app.command("run")
def run_current_strategy_command(
    save: bool = typer.Option(True, "--save/--no-save", help="是否保存调仓建议"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """一键执行当前策略：生成目标持仓并预览调仓建议。

    使用场景：
    - 每次决策前快速得到“当前策略 -> 目标持仓 -> 调仓建议”。

    示例：
    - uv run hiveflow current run
      用途：人类操盘前的一键闭环入口。
    - uv run hiveflow current run --no-save
      用途：只看建议不写库，先讨论再落地。
    - uv run hiveflow current run --output json --envelope
      用途：把完整闭环结果交给 AI/Skills 做二次决策。
    """
    if json_schema:
        _print_json_schema("current.run")
        return

    output_format = _validate_output_format(output)
    current = show_current_strategy().current_strategy
    if not current:
        raise typer.BadParameter("当前策略未设置，请先执行 current set-strategy。")

    generated = generate_targets_for_strategy(strategy_name=current)
    preview = preview_rebalance(strategy=current, save=save)
    payload = {
        "strategy": current,
        "targets_generated": generated.generated,
        "template_source": generated.template_source,
        "suggestions_count": len(preview.suggestions),
        "saved": preview.saved,
        "preview": preview.to_dict(),
    }
    record_decision_log(
        summary=f"执行当前策略：{current}",
        decision_type="current-run",
        notes=f"targets={generated.generated}, suggestions={len(preview.suggestions)}, save={save}",
    )
    if output_format == "json":
        _print_json(payload=payload, command="current.run", envelope=envelope)
        return
    typer.echo(
        f"已执行当前策略：{current}；目标条数={generated.generated}；"
        f"建议条数={len(preview.suggestions)}；已保存={'是' if preview.saved else '否'}"
    )


@app.command("summary")
def summary_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """输出当前数据库里的真实状态摘要。"""
    if json_schema:
        _print_json_schema("summary")
        return

    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    stats = get_summary_stats()
    payload = stats.to_dict()
    risk_count = stats.risk_signals_count
    suggestion_count = stats.rebalance_suggestions_count

    if output_format == "json":
        _print_json(payload=payload, command="summary", envelope=envelope)
        return

    if ui_theme == "minimal":
        lines = [
            "HiveFlow 状态摘要",
            f"- 持仓数量: {stats.positions_count}",
            f"- 策略数量: {stats.strategies_count}",
            f"- 席位数量: {stats.slots_count}",
            f"- 启用席位数量: {stats.enabled_slots_count}",
            f"- 当前策略: {stats.current_strategy or '未设置'}",
            f"- 持仓总市值: {stats.total_market_value:.2f}",
            f"- 目标持仓数量: {stats.target_allocations_count}",
            f"- 风险信号数量: {risk_count}",
            f"- 风险分布: 高 {stats.risk_high_count} / 中 {stats.risk_medium_count} / 低 {stats.risk_low_count}",
            f"- 调仓建议数量: {suggestion_count}",
            f"- 决策日志数量: {stats.decision_logs_count}",
        ]
        typer.echo("\n".join(lines))
        return

    risk_style = _level_style(risk_count, medium_threshold=1, high_threshold=3)
    suggestion_style = _level_style(suggestion_count, medium_threshold=1, high_threshold=3)

    lines = [
        "[bold #5fd75f]>> HIVEFLOW SYSTEM STATUS[/bold #5fd75f]",
        f"[#5f875f]- 持仓数量:[/#5f875f] [bold #87ff87]{stats.positions_count}[/bold #87ff87]",
        f"[#5f875f]- 策略数量:[/#5f875f] [bold #87ff87]{stats.strategies_count}[/bold #87ff87]",
        f"[#5f875f]- 席位数量:[/#5f875f] [bold #87ff87]{stats.slots_count}[/bold #87ff87]",
        (
            f"[#5f875f]- 启用席位数量:[/#5f875f] "
            f"[bold #87ff87]{stats.enabled_slots_count}[/bold #87ff87]"
        ),
        (
            f"[#5f875f]- 当前策略:[/#5f875f] "
            f"[bold #87ff87]{stats.current_strategy or '未设置'}[/bold #87ff87]"
        ),
        (
            f"[#5f875f]- 持仓总市值:[/#5f875f] "
            f"[bold #87ff87]{stats.total_market_value:.2f}[/bold #87ff87]"
        ),
        (
            f"[#5f875f]- 目标持仓数量:[/#5f875f] "
            f"[bold #87ff87]{stats.target_allocations_count}[/bold #87ff87]"
        ),
        f"[#5f875f]- 风险信号数量:[/#5f875f] [{risk_style}]{risk_count}[/{risk_style}]",
        (
            "[#5f875f]- 风险分布:[/#5f875f] "
            f"[bold red]高 {stats.risk_high_count}[/bold red] / "
            f"[bold yellow]中 {stats.risk_medium_count}[/bold yellow] / "
            f"[bold bright_green]低 {stats.risk_low_count}[/bold bright_green]"
        ),
        (
            f"[#5f875f]- 调仓建议数量:[/#5f875f] "
            f"[{suggestion_style}]{suggestion_count}[/{suggestion_style}]"
        ),
        (
            f"[#5f875f]- 决策日志数量:[/#5f875f] "
            f"[bold #87ff87]{stats.decision_logs_count}[/bold #87ff87]"
        ),
    ]
    console.print(
        Panel(
            "\n".join(lines),
            border_style="#5f875f",
            title="[bold #5fd75f]:: SUMMARY ::[/bold #5fd75f]",
            title_align="left",
        )
    )


@positions_app.command("add")
def add_position_command(
    symbol: str = typer.Option(..., help="标的代码"),
    quantity: float = typer.Option(..., help="持仓数量"),
    market_value: float = typer.Option(..., help="持仓市值"),
    weight: float = typer.Option(..., help="持仓权重（0~1）"),
) -> None:
    """新增一条持仓记录。"""
    add_position(symbol=symbol, quantity=quantity, market_value=market_value, weight=weight)
    typer.echo("Position added.")


@positions_app.command("list")
def list_positions_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """列出当前所有持仓记录。"""
    if json_schema:
        _print_json_schema("positions.list")
        return

    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    positions = list_positions()

    if not positions:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无持仓记录。")
        return

    if output_format == "json":
        payload = [position.to_dict() for position in positions]
        _print_json(payload=payload, command="positions.list", envelope=envelope)
        return

    if ui_theme == "minimal":
        table = Table(
            title="当前持仓",
            show_lines=False,
            box=box.SIMPLE,
        )
        table.add_column("标的", justify="left")
        table.add_column("数量", justify="right")
        table.add_column("市值", justify="right")
        table.add_column("权重", justify="right")
    else:
        table = Table(
            title="[bold #5fd75f]:: POSITIONS ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("数量", justify="right", style="#5f875f")
        table.add_column("市值", justify="right", style="#5f875f")
        table.add_column("权重", justify="right", style="#5f875f")

    for position in positions:
        table.add_row(
            position.symbol,
            f"{position.quantity:.6f}",
            f"{position.market_value:.2f}",
            f"{position.weight:.2%}",
        )
    console.print(table)


@positions_app.command("import")
def import_positions_command(
    file: Path = typer.Option(..., "--file", "-f", help="CSV 文件路径"),
    mode: str = typer.Option("append", "--mode", "-m", help="导入模式：append/replace"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从 CSV 导入持仓记录。"""
    output_format = _validate_output_format(output)
    import_mode = _validate_import_mode(mode)
    try:
        result = import_positions_from_csv(file=file, mode=import_mode)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"导入持仓 {result.imported} 条（模式：{result.mode}）",
        decision_type="positions-import",
        notes=f"file={file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"导入完成：{result.imported} 条（模式：{result.mode}）。")


@positions_app.command("drift")
def positions_drift_command(
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="指定策略名称（不传则使用当前策略）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """检测实际持仓与目标持仓的偏离等级。

    使用场景：
    - 快速定位最该处理的仓位，优先处理 high 偏离。

    示例：
    - uv run hiveflow positions drift
      用途：用当前策略快速查看偏离优先级。
    - uv run hiveflow positions drift --strategy "进攻突破策略"
      用途：只看某个策略对应的偏离，不受其它策略干扰。
    - uv run hiveflow positions drift --output json --envelope
      用途：把偏离结果结构化喂给 AI/Skills。
    """
    if json_schema:
        _print_json_schema("positions.drift")
        return

    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    effective_strategy = strategy or show_current_strategy().current_strategy
    if not effective_strategy:
        raise typer.BadParameter("未指定策略，且当前策略未设置。")

    items = analyze_positions_drift(strategy_name=effective_strategy)
    payload = {
        "strategy": effective_strategy,
        "count": len(items),
        "items": [item.to_dict() for item in items],
    }
    if output_format == "json":
        _print_json(payload=payload, command="positions.drift", envelope=envelope)
        return

    if ui_theme == "minimal":
        table = Table(title="持仓偏离", show_lines=False, box=box.SIMPLE)
        table.add_column("标的", justify="left")
        table.add_column("实际权重", justify="right")
        table.add_column("目标权重", justify="right")
        table.add_column("偏离", justify="right")
        table.add_column("等级", justify="left")
        table.add_column("建议", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: POSITION DRIFT ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("实际权重", justify="right", style="#5f875f")
        table.add_column("目标权重", justify="right", style="#5f875f")
        table.add_column("偏离", justify="right", style="#5f875f")
        table.add_column("等级", justify="left", style="#5f875f")
        table.add_column("建议", justify="left", style="#87ff87")
    for item in items:
        table.add_row(
            item.symbol,
            f"{item.actual_weight:.2%}",
            f"{item.target_weight:.2%}",
            f"{item.delta:+.2%}",
            _drift_level_label(item.drift_level),
            _action_label(item.action),
        )
    console.print(table)
    typer.echo(f"策略={effective_strategy}；偏离项={len(items)}")


@positions_app.command("template")
def export_positions_template_command(
    file: Path = typer.Option(
        Path("positions.csv"),
        "--file",
        "-f",
        help="模板输出路径（默认：./positions.csv）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出持仓 CSV 模板文件。"""
    output_format = _validate_output_format(output)
    result = export_positions_template(file=file)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"模板已生成：{result.file}")


@risk_app.command("list")
def list_risk_signals_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """列出当前所有风险信号记录。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    signals = list_risk_signals()
    if not signals:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无风险信号记录。")
        return

    if output_format == "json":
        payload = [signal.to_dict() for signal in signals]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if ui_theme == "minimal":
        table = Table(title="风险信号", show_lines=False, box=box.SIMPLE)
        table.add_column("标的", justify="left")
        table.add_column("风险水位", justify="left")
        table.add_column("风险评分", justify="right")
        table.add_column("备注", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: RISK SIGNALS ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("风险水位", justify="left", style="#5f875f")
        table.add_column("风险评分", justify="right", style="#5f875f")
        table.add_column("备注", justify="left", style="#5f875f")

    for signal in signals:
        table.add_row(
            signal.symbol,
            signal.waterline,
            f"{signal.score:.4f}",
            signal.note or "-",
        )
    console.print(table)


@risk_app.command("import")
def import_risk_signals_command(
    file: Path = typer.Option(..., "--file", "-f", help="CSV 文件路径"),
    mode: str = typer.Option("append", "--mode", "-m", help="导入模式：append/replace"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从 CSV 导入风险信号。"""
    output_format = _validate_output_format(output)
    import_mode = _validate_import_mode(mode)
    try:
        result = import_risk_signals_from_csv(file=file, mode=import_mode)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"导入风险信号 {result.imported} 条（模式：{result.mode}）",
        decision_type="risk-import",
        notes=f"file={file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"风险导入完成：{result.imported} 条（模式：{result.mode}）。")


@risk_app.command("template")
def export_risk_template_command(
    file: Path = typer.Option(
        Path("risk-signals.csv"),
        "--file",
        "-f",
        help="模板输出路径（默认：./risk-signals.csv）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出风险信号 CSV 模板。"""
    output_format = _validate_output_format(output)
    result = export_risk_template(file=file)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"风险模板已生成：{result.file}")


@targets_app.command("list")
def list_targets_command(
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="按策略名称过滤（可选）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """列出当前所有目标持仓记录。"""
    if json_schema:
        _print_json_schema("targets.list")
        return

    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    targets = list_target_allocations(strategy_name=strategy)
    if not targets:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无目标持仓记录。")
        return

    if output_format == "json":
        payload = [target.to_dict() for target in targets]
        _print_json(payload=payload, command="targets.list", envelope=envelope)
        return

    if ui_theme == "minimal":
        table = Table(title="目标持仓", show_lines=False, box=box.SIMPLE)
        table.add_column("策略", justify="left")
        table.add_column("类型", justify="left")
        table.add_column("维度", justify="left")
        table.add_column("标的", justify="left")
        table.add_column("目标权重", justify="right")
    else:
        table = Table(
            title="[bold #5fd75f]:: TARGET ALLOCATIONS ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("策略", justify="left", style="#5f875f")
        table.add_column("类型", justify="left", style="#5f875f")
        table.add_column("维度", justify="left", style="#5f875f")
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("目标权重", justify="right", style="#5f875f")

    for target in targets:
        table.add_row(
            target.strategy_name,
            target.strategy_type or "-",
            target.dimension or "-",
            target.symbol,
            f"{target.target_weight:.2%}",
        )
    console.print(table)


@targets_app.command("import")
def import_targets_command(
    file: Path = typer.Option(..., "--file", "-f", help="CSV 文件路径"),
    mode: str = typer.Option("append", "--mode", "-m", help="导入模式：append/replace"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从 CSV 导入目标持仓。"""
    output_format = _validate_output_format(output)
    import_mode = _validate_import_mode(mode)
    try:
        result = import_target_allocations_from_csv(file=file, mode=import_mode)
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"导入目标持仓 {result.imported} 条（模式：{result.mode}）",
        decision_type="targets-import",
        notes=f"file={file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"目标持仓导入完成：{result.imported} 条（模式：{result.mode}）。")


@targets_app.command("template")
def export_targets_template_command(
    file: Path = typer.Option(
        Path("target-allocations.csv"),
        "--file",
        "-f",
        help="模板输出路径（默认：./target-allocations.csv）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出目标持仓 CSV 模板。"""
    output_format = _validate_output_format(output)
    result = export_target_template(file=file)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"目标持仓模板已生成：{result.file}")


@targets_app.command("template-show")
def show_target_template_config_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """查看目标模板配置。"""
    output_format = _validate_output_format(output)
    config_view = get_target_template_config()
    payload = config_view.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"模板文件：{config_view.file}")
    typer.echo(f"类型模板数：{len(config_view.type_presets)}")
    typer.echo(f"维度模板数：{len(config_view.dimension_presets)}")


@targets_app.command("template-set")
def set_target_template_config_command(
    scope: str = typer.Option(..., "--scope", help="模板作用域：type/dimension"),
    key: str = typer.Option(..., "--key", help="模板键名，如 进攻型 或 趋势|动量"),
    weights: str = typer.Option(..., "--weights", help="权重串：BTC=0.5,ETH=0.3,USDT=0.2"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """设置单条目标模板配置。"""
    output_format = _validate_output_format(output)
    parsed_weights = _parse_weights(weights)
    try:
        result = set_target_template_preset(scope=scope, key=key, weights=parsed_weights)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"更新目标模板：{result.scope}/{result.key}",
        decision_type="targets-template-set",
        notes=f"file={result.file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"模板已更新：{result.scope}/{result.key} -> {result.weights}")


@targets_app.command("template-rollback")
def rollback_target_template_config_command(
    version: int | None = typer.Option(
        None,
        "--version",
        help="回滚到指定版本号（不传默认回滚到最近快照）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """回滚目标模板配置到历史快照。

    使用场景：
    - 模板误改后一键恢复到可用版本。

    示例：
    - uv run hiveflow targets template-rollback
      用途：回到最近一次快照（最快止损）。
    - uv run hiveflow targets template-rollback --version 2
      用途：精确恢复到已知稳定版本。
    - uv run hiveflow targets template-rollback --output json
      用途：在流水线中记录回滚事件。
    """
    if json_schema:
        _print_json_schema("targets.template-rollback")
        return

    output_format = _validate_output_format(output)
    try:
        result = rollback_target_template(version=version)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"回滚目标模板到版本 {result.restored_version}",
        decision_type="targets-template-rollback",
        notes=f"file={result.file}",
    )

    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="targets.template-rollback", envelope=envelope)
        return
    typer.echo(f"模板已回滚：version={result.restored_version} -> {result.file}")


@targets_app.command("generate")
def generate_targets_command(
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="策略名称（不传则使用当前策略）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """根据策略自动生成目标持仓。

    使用场景：
    - 策略切换后，快速生成最新目标仓位。

    示例：
    - uv run hiveflow targets generate
      用途：使用“当前策略”生成目标持仓。
    - uv run hiveflow targets generate --strategy "进攻突破策略"
      用途：强制按指定策略生成，不依赖当前策略状态。
    - uv run hiveflow targets generate --output json --envelope
      用途：将生成结果给 AI/Skills 继续处理。
    """
    if json_schema:
        _print_json_schema("targets.generate")
        return

    output_format = _validate_output_format(output)
    effective_strategy = strategy or show_current_strategy().current_strategy
    if not effective_strategy:
        raise typer.BadParameter("未指定策略，且当前策略未设置。")

    try:
        result = generate_targets_for_strategy(strategy_name=effective_strategy)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"基于策略自动生成目标持仓 {result.generated} 条",
        decision_type="targets-generate",
        notes=f"strategy={result.strategy}",
    )

    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="targets.generate", envelope=envelope)
        return
    typer.echo(
        "目标持仓已生成："
        f"策略={result.strategy}，类型={result.strategy_type}，维度={result.dimension or '-'}，"
        f"模板来源={result.template_source}，条数={result.generated}"
    )


@rebalance_app.command("preview")
def preview_rebalance_command(
    strategy: str | None = typer.Option(
        None,
        "--strategy",
        "-s",
        help="只预览指定策略的目标持仓（默认使用全部目标持仓）",
    ),
    save: bool = typer.Option(False, "--save", help="是否保存本次调仓建议到数据库"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """预览调仓建议。

    使用场景：
    - 执行动作前先看建议，确认风险与优先级。

    示例：
    - uv run hiveflow rebalance preview
      用途：用当前策略做一次人工决策前检查。
    - uv run hiveflow rebalance preview --strategy "进攻突破策略" --save
      用途：指定策略并落库，供后续 summary/日志复盘。
    - uv run hiveflow rebalance preview --output json --envelope
      用途：输出结构化建议给 AI/自动化流程。
    """
    if json_schema:
        _print_json_schema("rebalance.preview")
        return

    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    effective_strategy = strategy or show_current_strategy().current_strategy
    result = preview_rebalance(strategy=effective_strategy, save=save)
    payload = result.to_dict()

    if output_format == "json":
        _print_json(payload=payload, command="rebalance.preview", envelope=envelope)
        return

    if result.strategy:
        typer.echo(
            f"策略={result.strategy}，类型={result.strategy_type or '-'}，维度={result.dimension or '-'}"
        )

    if not result.suggestions:
        typer.echo("暂无调仓建议。")
        return

    if ui_theme == "minimal":
        table = Table(title="调仓建议预览", show_lines=False, box=box.SIMPLE)
        table.add_column("标的", justify="left")
        table.add_column("偏差", justify="right")
        table.add_column("动作", justify="left")
        table.add_column("优先级", justify="left")
        table.add_column("风险水位", justify="left")
    else:
        table = Table(
            title="[bold #5fd75f]:: REBALANCE PREVIEW ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("偏差", justify="right", style="#5f875f")
        table.add_column("动作", justify="left", style="#87ff87")
        table.add_column("优先级", justify="left", style="#5f875f")
        table.add_column("风险水位", justify="left", style="#5f875f")

    for item in result.suggestions:
        risk_percent = (
            f"{item.risk_score * 100:.2f}%"
            if item.risk_score is not None
            else "-"
        )
        table.add_row(
            item.symbol,
            f"{item.delta:+.2%}",
            _action_label(item.action),
            _priority_label(item.priority),
            risk_percent,
        )
    console.print(table)
    typer.echo(f"建议数量：{len(result.suggestions)}；已保存：{'是' if result.saved else '否'}")


@market_data_app.command("template")
def export_market_data_template_command(
    file: Path = typer.Option(
        Path("prices.csv"),
        "--file",
        "-f",
        help="模板输出路径（默认：./prices.csv）",
    ),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导出行情 CSV 模板。"""
    output_format = _validate_output_format(output)
    result = export_market_data_template(file=file)
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"行情模板已生成：{result.file}")


@market_data_app.command("validate")
def validate_market_data_command(
    file: Path = typer.Option(..., "--file", "-f", help="待校验 CSV 路径"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
) -> None:
    """校验行情 CSV 是否符合 HiveFlow 契约。"""
    if json_schema:
        _print_json_schema("market-data.validate")
        return

    output_format = _validate_output_format(output)
    try:
        result = validate_market_data_csv(file=file)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    payload = result.to_dict()
    if output_format == "json":
        _print_json(payload=payload, command="market-data.validate", envelope=envelope)
        return

    if result.valid:
        typer.echo(f"校验通过：{result.rows} 行有效数据。")
        return
    typer.echo(f"校验失败：{len(result.errors)} 个问题。")
    for item in result.errors:
        typer.echo(f"- {item}")


@market_data_app.command("import")
def import_market_data_command(
    file: Path = typer.Option(..., "--file", "-f", help="CSV 文件路径"),
    mode: str = typer.Option("append", "--mode", "-m", help="导入模式：append/replace"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """导入行情 CSV 到数据库。"""
    output_format = _validate_output_format(output)
    import_mode = _validate_import_mode(mode)
    try:
        result = import_market_data_csv(file=file, mode=import_mode)
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"导入行情 {result.imported} 条（模式：{result.mode}）",
        decision_type="market-data-import",
        notes=f"file={file}",
    )
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(f"行情导入完成：{result.imported} 条（模式：{result.mode}）。")


@market_data_app.command("list")
def list_market_data_command(
    symbol: str | None = typer.Option(None, "--symbol", "-s", help="按标的过滤（可选）"),
    limit: int = typer.Option(100, "--limit", help="最多返回条数"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """查看已导入行情。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    row_limit = _validate_limit(limit)
    rows = list_market_bars(symbol=symbol, limit=row_limit)
    if output_format == "json":
        typer.echo(json.dumps([item.to_dict() for item in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        typer.echo("暂无行情记录。")
        return
    if ui_theme == "minimal":
        table = Table(title="行情数据", show_lines=False, box=box.SIMPLE)
        table.add_column("标的", justify="left")
        table.add_column("时间", justify="left")
        table.add_column("开", justify="right")
        table.add_column("高", justify="right")
        table.add_column("低", justify="right")
        table.add_column("收", justify="right")
        table.add_column("量", justify="right")
    else:
        table = Table(
            title="[bold #5fd75f]:: MARKET DATA ::[/bold #5fd75f]",
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("时间", justify="left", style="#5f875f")
        table.add_column("开", justify="right", style="#5f875f")
        table.add_column("高", justify="right", style="#5f875f")
        table.add_column("低", justify="right", style="#5f875f")
        table.add_column("收", justify="right", style="#5f875f")
        table.add_column("量", justify="right", style="#5f875f")
    for item in rows:
        table.add_row(
            item.symbol,
            item.timestamp,
            f"{item.open:.4f}",
            f"{item.high:.4f}",
            f"{item.low:.4f}",
            f"{item.close:.4f}",
            f"{item.volume:.2f}",
        )
    console.print(table)


@market_data_app.command("summary")
def summary_market_data_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """查看行情数据汇总。"""
    output_format = _validate_output_format(output)
    result = summarize_market_data()
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(
        f"行情汇总：symbols={result.symbols_count} bars={result.bars_count} latest={result.latest_timestamp or '-'}"
    )


@backtest_app.command("run")
def run_backtest_command(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名称"),
    file: Path = typer.Option(..., "--file", "-f", help="行情 CSV 文件路径"),
    fee_bps: float = typer.Option(0.0, "--fee-bps", help="交易费率（基点）"),
    slippage_bps: float = typer.Option(0.0, "--slippage-bps", help="滑点（基点）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """运行一次策略回测。"""
    output_format = _validate_output_format(output)
    try:
        result = run_backtest_for_strategy(
            strategy_name=strategy,
            prices_file=file,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    record_decision_log(
        summary=f"执行回测：{strategy}",
        decision_type="backtest-run",
        notes=f"file={file}, periods={result.periods}",
    )
    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    typer.echo(
        f"回测完成：strategy={result.strategy_name} "
        f"return={result.total_return:.2%} "
        f"mdd={result.max_drawdown:.2%} "
        f"sharpe={result.sharpe:.2f}"
    )


@backtest_app.command("list")
def list_backtest_command(
    strategy: str | None = typer.Option(None, "--strategy", "-s", help="按策略过滤（可选）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """列出历史回测结果。"""
    output_format = _validate_output_format(output)
    rows = list_backtest_results(strategy_name=strategy)
    payload = [item.to_dict() for item in rows]
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if not rows:
        typer.echo("暂无回测记录。")
        return
    table = Table(title="回测记录", show_lines=False, box=box.SIMPLE)
    table.add_column("策略", justify="left")
    table.add_column("周期", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("Sharpe", justify="right")
    table.add_column("时间", justify="left")
    for item in rows:
        table.add_row(
            item.strategy_name,
            str(item.periods),
            f"{item.total_return:.2%}",
            f"{item.max_drawdown:.2%}",
            f"{item.sharpe:.2f}",
            item.created_at,
        )
    console.print(table)


@app.command()
def sync(
    days: int | None = typer.Option(None, "--days", help="同步最近 N 天 K 线（最大 100）"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """从 OKX 拉取最新持仓和价格，写入本地数据库。"""
    settings = Settings()
    if not (settings.okx_api_key and settings.okx_api_secret and settings.okx_api_passphrase):
        console.print(
            "错误：未配置 OKX API Key。请在 .env 中设置：\n"
            "  HIVEFLOW_OKX_API_KEY / HIVEFLOW_OKX_API_SECRET / HIVEFLOW_OKX_API_PASSPHRASE",
            style="bold red",
        )
        raise typer.Exit(code=1)
    if days is not None and not (1 <= days <= 100):
        console.print("错误：--days 必须在 1 到 100 之间（OKX 单次上限）。", style="bold red")
        raise typer.Exit(code=1)

    provider = OkxProvider(
        api_key=settings.okx_api_key,
        api_secret=settings.okx_api_secret,
        passphrase=settings.okx_api_passphrase,
    )
    try:
        result = sync_from_okx(provider=provider, settings=settings, days=days)
    except (OkxAuthError, OkxTimeoutError, OkxRateLimitError) as e:
        console.print(f"错误：{e}", style="bold red")
        raise typer.Exit(code=1)

    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False))
        return

    console.print(f"[bold green]同步完成[/bold green]  {result.synced_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    console.print(f"持仓：{result.positions_synced} 个币种  总估值：{result.total_value_usdt:,.2f} USDT")
    console.print(f"价格：{result.prices_synced} 条记录已更新")
    if result.candles_synced > 0:
        console.print(f"K 线：{result.candles_synced} 条历史记录已写入")


def _load_check_data(settings: Settings) -> tuple[list, dict]:
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.domain.positions import Position
    create_all_tables(settings)
    with get_session(settings) as session:
        positions = list(session.exec(select(Position)).all())
        all_bars = list(session.exec(select(MarketBar)).all())
    bars_by_symbol: dict[str, list] = {}
    for bar in all_bars:
        bars_by_symbol.setdefault(bar.symbol, []).append(bar)
    return positions, bars_by_symbol


@app.command()
def check(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """检查持仓风险状态，输出健康结论（退出码始终为 0）。"""
    settings = Settings()
    positions, bars_by_symbol = _load_check_data(settings)
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)

    if output == "json":
        payload = {
            "verdict": result.verdict,
            "summary": result.verdict_summary,
            "has_no_history": result.has_no_history,
            "signals": [
                {"symbol": s.symbol, "max_drawdown_7d_pct": round(s.max_drawdown_7d * 100, 2),
                 "alert_level": s.alert_level.value, "action_hint": s.action_hint}
                for s in result.signals
            ],
        }
        console.print(json.dumps(payload, ensure_ascii=False))
        return

    from datetime import date
    console.rule(f"今日持仓健康检查  {date.today()}")
    console.print()
    style = {"safe": "bold green", "watch": "bold yellow", "danger": "bold red"}[result.verdict]
    icon = {"safe": "✅", "watch": "⚠️", "danger": "🔴"}[result.verdict]
    console.print(f"[{style}][结论] {icon}  {result.verdict_summary}[/{style}]")
    console.print()

    if result.has_no_history:
        console.print("[yellow]提示：未检测到历史行情数据，请先执行 hiveflow sync --days 30 以启用风险分析。[/yellow]")
        return

    if result.signals:
        table = Table(box=box.SIMPLE)
        table.add_column("币种", style="bold")
        table.add_column("7日最大回撤", justify="right")
        table.add_column("状态")
        for sig in result.signals:
            label, color = {
                AlertLevel.NORMAL: ("正常", "green"),
                AlertLevel.WARNING: ("⚠️ 注意", "yellow"),
                AlertLevel.DANGER: ("🔴 危险", "red"),
            }[sig.alert_level]
            table.add_row(sig.symbol, f"{sig.max_drawdown_7d * 100:.1f}%", f"[{color}]{label}[/{color}]")
        console.print(table)

    actions = [s.action_hint for s in result.signals if s.action_hint]
    if actions:
        console.print("[bold]建议动作[/bold]")
        for hint in actions:
            console.print(f"  → {hint}")


app.add_typer(positions_app, name="positions")
app.add_typer(risk_app, name="risk")
app.add_typer(targets_app, name="targets")
app.add_typer(rebalance_app, name="rebalance")
app.add_typer(logs_app, name="logs")
app.add_typer(strategies_app, name="strategies")
app.add_typer(slots_app, name="slots")
app.add_typer(current_app, name="current")
app.add_typer(market_data_app, name="market-data")
app.add_typer(backtest_app, name="backtest")


def run() -> None:
    """CLI 入口函数，供 pyproject 脚本调用。"""
    app()


if __name__ == "__main__":
    run()
