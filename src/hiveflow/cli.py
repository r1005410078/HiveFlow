import typer

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.services.bootstrap import bootstrap_all

app = typer.Typer(help="HiveFlow 本地资产决策系统。")


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
def summary_command() -> None:
    """输出最小可运行版本的状态摘要。"""
    lines = [
        "HiveFlow Summary",
        "- Positions: demo data",
        "- Target allocations: demo data",
        "- Risk state: demo data",
        "- Rebalance suggestions: demo data",
    ]
    typer.echo("\n".join(lines))


def run() -> None:
    """CLI 入口函数，供 pyproject 脚本调用。"""
    app()


if __name__ == "__main__":
    run()
