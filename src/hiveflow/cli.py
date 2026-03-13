import json
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from hiveflow.application.decision_logs import record_decision_log
from hiveflow.application.positions import add_position
from hiveflow.application.positions import export_positions_template
from hiveflow.application.positions import import_positions_from_csv
from hiveflow.application.positions import list_positions
from hiveflow.application.rebalance import preview_rebalance
from hiveflow.application.risk import export_risk_template
from hiveflow.application.risk import import_risk_signals_from_csv
from hiveflow.application.risk import list_risk_signals
from hiveflow.application.summary import get_summary_stats
from hiveflow.application.targets import export_target_template
from hiveflow.application.targets import import_target_allocations_from_csv
from hiveflow.application.targets import list_target_allocations
from hiveflow.services.bootstrap import bootstrap_all

app = typer.Typer(help="HiveFlow 本地资产决策系统。")
positions_app = typer.Typer(help="持仓管理命令。")
risk_app = typer.Typer(help="风险信号管理命令。")
targets_app = typer.Typer(help="目标持仓管理命令。")
rebalance_app = typer.Typer(help="调仓建议命令。")
console = Console()


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


@app.command("summary")
def summary_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """输出当前数据库里的真实状态摘要。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    stats = get_summary_stats()
    payload = stats.to_dict()
    risk_count = stats.risk_signals_count
    suggestion_count = stats.rebalance_suggestions_count

    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if ui_theme == "minimal":
        lines = [
            "HiveFlow 状态摘要",
            f"- 持仓数量: {stats.positions_count}",
            f"- 持仓总市值: {stats.total_market_value:.2f}",
            f"- 目标持仓数量: {stats.target_allocations_count}",
            f"- 风险信号数量: {risk_count}",
            f"- 风险分布: 高 {stats.risk_high_count} / 中 {stats.risk_medium_count} / 低 {stats.risk_low_count}",
            f"- 调仓建议数量: {suggestion_count}",
        ]
        typer.echo("\n".join(lines))
        return

    risk_style = _level_style(risk_count, medium_threshold=1, high_threshold=3)
    suggestion_style = _level_style(suggestion_count, medium_threshold=1, high_threshold=3)

    lines = [
        "[bold #5fd75f]>> HIVEFLOW SYSTEM STATUS[/bold #5fd75f]",
        f"[#5f875f]- 持仓数量:[/#5f875f] [bold #87ff87]{stats.positions_count}[/bold #87ff87]",
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
) -> None:
    """列出当前所有持仓记录。"""
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
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
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

    payload = result.to_dict()
    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo(f"导入完成：{result.imported} 条（模式：{result.mode}）。")


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
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
) -> None:
    """列出当前所有目标持仓记录。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    targets = list_target_allocations()
    if not targets:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无目标持仓记录。")
        return

    if output_format == "json":
        payload = [target.to_dict() for target in targets]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if ui_theme == "minimal":
        table = Table(title="目标持仓", show_lines=False, box=box.SIMPLE)
        table.add_column("策略", justify="left")
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
        table.add_column("标的", justify="left", style="#87ff87")
        table.add_column("目标权重", justify="right", style="#5f875f")

    for target in targets:
        table.add_row(
            target.strategy_name,
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
) -> None:
    """预览调仓建议。"""
    output_format = _validate_output_format(output)
    ui_theme = _validate_theme(theme)
    result = preview_rebalance(strategy=strategy, save=save)
    payload = result.to_dict()

    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not result.suggestions:
        typer.echo("暂无调仓建议。")
        return

    if ui_theme == "minimal":
        table = Table(title="调仓建议预览", show_lines=False, box=box.SIMPLE)
        table.add_column("标的", justify="left")
        table.add_column("偏差", justify="right")
        table.add_column("动作", justify="left")
        table.add_column("优先级", justify="left")
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

    for item in result.suggestions:
        table.add_row(
            item.symbol,
            f"{item.delta:+.2%}",
            item.action,
            item.priority,
        )
    console.print(table)
    typer.echo(f"建议数量：{len(result.suggestions)}；已保存：{'是' if result.saved else '否'}")


app.add_typer(positions_app, name="positions")
app.add_typer(risk_app, name="risk")
app.add_typer(targets_app, name="targets")
app.add_typer(rebalance_app, name="rebalance")


def run() -> None:
    """CLI 入口函数，供 pyproject 脚本调用。"""
    app()


if __name__ == "__main__":
    run()
