import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.suggestions import RebalanceSuggestion
from hiveflow.services.bootstrap import bootstrap_all

app = typer.Typer(help="HiveFlow 本地资产决策系统。")
positions_app = typer.Typer(help="持仓管理命令。")
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
    create_all_tables()
    with get_session() as session:
        session.add(
            DecisionLog(
                summary=summary,
                decision_type=decision_type,
                notes=notes,
            )
        )
        session.commit()
    typer.echo("Decision log recorded.")


@app.command("summary")
def summary_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """输出当前数据库里的真实状态摘要。"""
    output_format = _validate_output_format(output)
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()
        target_allocations = session.exec(select(TargetAllocation)).all()
        risk_signals = session.exec(select(RiskSignal)).all()
        rebalance_suggestions = session.exec(select(RebalanceSuggestion)).all()

    total_market_value = sum(position.market_value for position in positions)
    risk_count = len(risk_signals)
    suggestion_count = len(rebalance_suggestions)

    payload = {
        "positions_count": len(positions),
        "total_market_value": round(total_market_value, 2),
        "target_allocations_count": len(target_allocations),
        "risk_signals_count": risk_count,
        "rebalance_suggestions_count": suggestion_count,
    }

    if output_format == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    risk_style = _level_style(risk_count, medium_threshold=1, high_threshold=3)
    suggestion_style = _level_style(suggestion_count, medium_threshold=1, high_threshold=3)

    lines = [
        "[bold cyan]HiveFlow 状态摘要[/bold cyan]",
        f"[green]- 持仓数量:[/green] [bold]{len(positions)}[/bold]",
        f"[green]- 持仓总市值:[/green] [bold]{total_market_value:.2f}[/bold]",
        f"[yellow]- 目标持仓数量:[/yellow] [bold]{len(target_allocations)}[/bold]",
        f"[magenta]- 风险信号数量:[/magenta] [{risk_style}]{risk_count}[/{risk_style}]",
        f"[red]- 调仓建议数量:[/red] [{suggestion_style}]{suggestion_count}[/{suggestion_style}]",
    ]
    console.print(
        Panel(
            "\n".join(lines),
            border_style="cyan",
            title="Summary",
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
    create_all_tables()
    with get_session() as session:
        session.add(
            Position(
                symbol=symbol.upper(),
                quantity=quantity,
                market_value=market_value,
                weight=weight,
            )
        )
        session.commit()
    typer.echo("Position added.")


@positions_app.command("list")
def list_positions_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """列出当前所有持仓记录。"""
    output_format = _validate_output_format(output)
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()

    if not positions:
        if output_format == "json":
            typer.echo("[]")
        else:
            typer.echo("暂无持仓记录。")
        return

    sorted_positions = sorted(positions, key=lambda item: item.symbol)
    if output_format == "json":
        payload = [
            {
                "symbol": position.symbol,
                "quantity": round(position.quantity, 6),
                "market_value": round(position.market_value, 2),
                "weight": round(position.weight, 6),
            }
            for position in sorted_positions
        ]
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(
        title="[bold cyan]当前持仓[/bold cyan]",
        show_lines=False,
        header_style="bold white",
        border_style="cyan",
    )
    table.add_column("标的", justify="left", style="bold yellow")
    table.add_column("数量", justify="right", style="green")
    table.add_column("市值", justify="right", style="bright_blue")
    table.add_column("权重", justify="right", style="magenta")

    for position in sorted_positions:
        table.add_row(
            position.symbol,
            f"{position.quantity:.6f}",
            f"{position.market_value:.2f}",
            f"{position.weight:.2%}",
        )
    console.print(table)


app.add_typer(positions_app, name="positions")


def run() -> None:
    """CLI 入口函数，供 pyproject 脚本调用。"""
    app()


if __name__ == "__main__":
    run()
