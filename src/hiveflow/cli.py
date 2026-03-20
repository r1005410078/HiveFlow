import json
from datetime import datetime, timezone
from time import perf_counter
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
from hiveflow.application.error_protocol import ErrorCode, build_error_payload, new_trace_id
from hiveflow.application.signals import (
    SIGNALS_BY_CATEGORY,
    SignalPipelineError,
    build_signal_category,
    build_signal_snapshot,
    signal_keys_of,
)
from hiveflow.application.system_logs import record_system_log
from hiveflow.application.style_backtest import StyleBacktestError, run_style_backtest_rank
from hiveflow.application.signal_snapshots import (
    get_signal_snapshot,
    list_signal_snapshots,
    save_signal_snapshot,
)
from hiveflow.application.style_backtest_results import (
    get_style_backtest_result,
    list_style_backtest_results,
    save_style_backtest_result,
)
from hiveflow.application.backtest import BacktestResultView
from hiveflow.application.backtest import get_backtest_result
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
from hiveflow.application.positions import list_grid_positions
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
from hiveflow.application.trade import TradeOrder, execute_trades
from hiveflow.application.skills import list_skills, install_skills, get_skills_dir, get_target_dir
from hiveflow.application.quant_strategies import (
    list_strategy_runs,
    run_quant_strategy,
)
from hiveflow.application.blend import (
    BlendConfigView,
    BlendRunResult,
    create_blend,
    delete_blend,
    get_blend,
    list_blends,
    run_blend,
    update_blend,
)
from hiveflow.application.risk_analysis import analyze_asset_risk, analyze_portfolio_risk
from hiveflow.application.perf import (
    PerfCompareResult,
    PortfolioSnapshotView,
    compare_with_backtest,
    list_snapshots,
    record_snapshot as _record_snapshot_impl,
)
from hiveflow.services.strategies import (
    BaseStrategy,
    BollingerBandStrategy,
    EqualWeightStrategy,
    MaxSharpeStrategy,
    MeanReversionStrategy,
    MinVarianceStrategy,
    MomentumStrategy,
    MovingAverageCrossStrategy,
    RiskParityStrategy,
)
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
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(curve: list[float], width: int = 40) -> str:
    """将权益曲线降采样到至多 width 个字符，映射到 8 级 Unicode 块字符。

    输出长度规则：
    - 若 len(curve) >= width：输出至多 width 个字符（完整表示曲线）
    - 若 len(curve) < width：输出 len(curve) 个字符（不补齐）
    - 若 len(curve) < 2：返回 width 个 '─'
    """
    if not curve or len(curve) < 2:
        return "─" * width
    step = max(1, -(-len(curve) // width))  # ceiling division without math import
    sampled = [
        sum(curve[i : i + step]) / len(curve[i : i + step])
        for i in range(0, len(curve), step)
    ][:width]
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return _SPARK_CHARS[0] * len(sampled)
    bucket = (hi - lo) / (len(_SPARK_CHARS) - 1)
    return "".join(
        _SPARK_CHARS[min(int((v - lo) / bucket), len(_SPARK_CHARS) - 1)]
        for v in sampled
    )


backtest_app = typer.Typer(help="策略回测命令。")
trade_app = typer.Typer(help="交易执行命令。")
skills_app = typer.Typer(name="skills", help="管理 AI Agent Skills。")
quant_app = typer.Typer(help="量化策略命令。")
blend_app = typer.Typer(help="多策略混合命令。")
risk_analysis_app = typer.Typer(help="资产与组合风险数据输出。")
perf_app = typer.Typer(help="实盘绩效追踪命令。")
signal_app = typer.Typer(help="信号系统命令。")
style_app = typer.Typer(help="风格回测排名命令。")
context_app = typer.Typer(help="Agent 上下文聚合命令。")
console = Console()
JSON_SCHEMA_VERSION = "1.0.0"

_SIGNAL_KEY_LABELS: dict[str, str] = {
    "golden_cross": "金叉",
    "death_cross": "死叉",
    "breakout_20d": "20日突破",
    "breakdown_20d": "20日跌破",
    "momentum_20d": "20日动量",
    "macd_cross": "MACD 交叉",
    "max_drawdown_7d": "7日最大回撤",
    "max_drawdown_30d": "30日最大回撤",
    "atr_volatility_14d": "14日 ATR 波动",
    "vol_regime_shift": "波动率状态切换",
    "concentration_risk": "集中度风险",
    "correlation_spike": "相关性抬升",
    "volume_breakout_confirm": "放量突破确认",
    "multi_timeframe_confirm": "多周期确认",
    "signal_consensus": "信号一致性",
    "trend_persistence": "趋势持续性",
    "market_regime_label": "市场状态标签",
    "trend_strength_adx": "ADX 趋势强度",
    "volatility_regime_label": "波动状态标签",
    "local_breadth_proxy": "本地宽度代理",
    "data_freshness": "数据新鲜度",
    "data_completeness": "数据完整度",
    "signal_stability": "信号稳定性",
    "confidence_score": "置信分数",
}

_SIGNAL_CATEGORY_LABELS: dict[str, str] = {
    "trend": "趋势",
    "risk": "风险",
    "confirm": "确认",
    "regime": "状态",
    "quality": "质量",
}

_SIGNAL_STATE_LABELS: dict[str, dict[str, str]] = {
    "trend": {"bullish": "看多", "neutral": "中性", "bearish": "看空"},
    "confirm": {"bullish": "看多", "neutral": "中性", "bearish": "看空"},
    "regime": {"bullish": "看多", "neutral": "中性", "bearish": "看空"},
    "risk": {"low": "低风险", "medium": "中风险", "high": "高风险"},
    "quality": {"good": "良好", "warning": "预警", "bad": "异常"},
}


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


def _validate_strict_source(value: str) -> str:
    """校验上下文来源严格模式。"""
    normalized = value.strip().lower()
    if normalized not in {"latest", "fresh"}:
        raise typer.BadParameter("strict-source 仅支持 latest 或 fresh。")
    return normalized


def _validate_positive_hours(value: int) -> int:
    """校验小时阈值参数。"""
    if value <= 0:
        raise typer.BadParameter("max-age-hours 必须大于 0。")
    return value


def _validate_strict_window(value: str) -> str:
    """校验窗口严格模式。"""
    normalized = value.strip().lower()
    if normalized not in {"all", "partial"}:
        raise typer.BadParameter("strict-window 仅支持 all 或 partial。")
    return normalized


def _parse_windows(value: str) -> tuple[int, ...]:
    """解析交易窗口参数（逗号分隔正整数）。"""
    if not value or not value.strip():
        raise typer.BadParameter("windows 不能为空，示例：24,7,30。")

    sizes: list[int] = []
    seen: set[int] = set()
    for part in value.split(","):
        token = part.strip()
        if not token:
            raise typer.BadParameter("windows 包含空值，示例：24,7,30。")
        try:
            size = int(token)
        except ValueError as exc:
            raise typer.BadParameter(f"windows 包含非整数值：{token}") from exc
        if size <= 0:
            raise typer.BadParameter("windows 仅支持大于 0 的整数。")
        if size in seen:
            continue
        seen.add(size)
        sizes.append(size)
    return tuple(sizes)


def _calc_age_hours(as_of_text: str) -> float | None:
    """计算 ISO 时间字符串距今小时数，解析失败返回 None。"""
    try:
        as_of_dt = datetime.fromisoformat(as_of_text)
    except ValueError:
        return None
    if as_of_dt.tzinfo is None:
        as_of_dt = as_of_dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - as_of_dt.astimezone(timezone.utc)).total_seconds() / 3600


def _decision_boundary_meta() -> dict[str, str]:
    """统一标记系统与 Agent 的职责边界。"""
    return {
        "system": "data_only",
        "agent": "analysis_and_decision",
    }


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


def _signal_key_label(signal_key: str) -> str:
    """信号键中文名（用于 pretty 输出）。"""
    return _SIGNAL_KEY_LABELS.get(signal_key, signal_key)


def _signal_state_label(category: str, state: str) -> str:
    """信号状态中文名（用于 pretty 输出）。"""
    return _SIGNAL_STATE_LABELS.get(category, {}).get(state, state)


def _emit_strict_failure(
    *,
    code: ErrorCode,
    context: str,
    message: str,
    details: dict,
    hint: dict | str | None,
    output: str,
) -> None:
    """统一输出严格模式失败对象，并记录系统日志。"""
    trace_id = new_trace_id()
    payload = build_error_payload(
        code=code,
        message=message,
        context=context,
        details=details,
        hint=hint,
        trace_id=trace_id,
    )
    record_system_log(
        trace_id=payload["trace_id"],
        error_code=payload["code"],
        context=payload["context"],
        message=payload["message"],
        details=payload["details"],
        hint=payload["hint"],
    )

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        console.print(f"[red]{message}[/red]")
        console.print(f"[dim]code={payload['code']} trace_id={payload['trace_id']}[/dim]")
    raise typer.Exit(1)


@signal_app.command("trend")
def signal_trend_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出趋势类信号。"""
    try:
        payload = build_signal_category("trend", settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.trend",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="趋势信号", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@signal_app.command("risk")
def signal_risk_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出风险类信号。"""
    try:
        payload = build_signal_category("risk", settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.risk",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="风险信号", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@signal_app.command("confirm")
def signal_confirm_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出确认类信号。"""
    try:
        payload = build_signal_category("confirm", settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.confirm",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="确认信号", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@signal_app.command("regime")
def signal_regime_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出市场状态类信号。"""
    try:
        payload = build_signal_category("regime", settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.regime",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="市场状态信号", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@signal_app.command("quality")
def signal_quality_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出质量类信号。"""
    try:
        payload = build_signal_category("quality", settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.quality",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="质量信号", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@signal_app.command("snapshot")
def signal_snapshot_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出聚合信号快照。"""
    app_settings = Settings()
    try:
        payload = build_signal_snapshot(settings=app_settings)
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context=exc.context or "signal.snapshot",
            message=exc.message,
            details=exc.details
            or {
                "strict_mode": True,
                "missing_signals": signal_keys_of(),
                "missing_categories": list(SIGNALS_BY_CATEGORY.keys()),
            },
            hint=exc.hint or {"action": "sync_and_compute_signals", "suggested_sync_days": 90},
            output=output,
        )
        return

    try:
        saved = save_signal_snapshot(payload, settings=app_settings)
    except Exception as exc:
        _emit_strict_failure(
            code=ErrorCode.STORAGE_WRITE_FAILED,
            context="signal.snapshot",
            message="信号快照落库失败，严格模式中断。",
            details={
                "strict_mode": True,
                "reason": str(exc),
            },
            hint={"action": "check_database_writable"},
            output=output,
        )
        return

    payload["id"] = saved.id
    payload["snapshot_id"] = saved.snapshot_id

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    console.print(
        f"[bold]信号快照[/bold] id={payload['id']} snapshot_id={payload['snapshot_id']} "
        f"as_of={payload['as_of']} symbol={payload['symbol']}"
    )
    cat_table = Table(title="分类统计", box=box.SIMPLE)
    cat_table.add_column("分类")
    cat_table.add_column("数量", justify="right")
    cat_table.add_column("触发数", justify="right")
    cat_table.add_column("平均置信度", justify="right")
    for category, stats in payload["category_metrics"].items():
        cat_table.add_row(
            _SIGNAL_CATEGORY_LABELS.get(category, category),
            str(stats["count"]),
            str(stats["triggered_count"]),
            f"{stats['confidence_avg']:.3f}",
        )
    console.print(cat_table)


@signal_app.command("history")
def signal_history_command(
    limit: int = typer.Option(20, "--limit", callback=_validate_limit, help="显示最近 N 条快照"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """查询信号快照历史。"""
    rows = list_signal_snapshots(limit=limit, settings=Settings())
    if output == "json":
        typer.echo(json.dumps([r.to_dict() for r in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        console.print("[yellow]暂无信号快照记录。[/yellow]")
        return
    table = Table(title="信号快照历史", box=box.SIMPLE)
    table.add_column("编号", justify="right")
    table.add_column("快照ID")
    table.add_column("快照时间")
    table.add_column("标的")
    table.add_column("信号数", justify="right")
    table.add_column("落库时间")
    for row in rows:
        table.add_row(
            str(row.id),
            row.snapshot_id,
            row.as_of,
            row.symbol,
            str(row.signals_count),
            row.created_at,
        )
    console.print(table)


@signal_app.command("show")
def signal_show_command(
    record_id: int = typer.Argument(..., help="快照记录 ID"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """按记录 ID 查看单条信号快照。"""
    try:
        payload = get_signal_snapshot(record_id=record_id, settings=Settings())
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    console.print(
        f"[bold]信号快照详情[/bold] id={payload['id']} snapshot_id={payload['snapshot_id']} "
        f"as_of={payload['as_of']} symbol={payload['symbol']}"
    )
    table = Table(title="信号列表", box=box.SIMPLE)
    table.add_column("信号键")
    table.add_column("状态")
    table.add_column("数值", justify="right")
    table.add_column("触发")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)


@style_app.command("backtest-rank")
def style_backtest_rank_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出风格回测排名。"""
    app_settings = Settings()
    try:
        payload = run_style_backtest_rank(settings=app_settings)
    except StyleBacktestError as exc:
        _emit_strict_failure(
            code=ErrorCode.STYLE_EVAL_FAILED,
            context=exc.context or "style.backtest-rank",
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
        )
        return

    try:
        saved = save_style_backtest_result(payload, settings=app_settings)
    except Exception as exc:
        _emit_strict_failure(
            code=ErrorCode.STORAGE_WRITE_FAILED,
            context="style.backtest-rank",
            message="风格回测结果落库失败，严格模式中断。",
            details={
                "strict_mode": True,
                "reason": str(exc),
            },
            hint={"action": "check_database_writable"},
            output=output,
        )
        return

    payload["id"] = saved.id
    payload["run_id"] = saved.run_id

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="风格回测排名", box=box.SIMPLE)
    table.add_column("排名", justify="right")
    table.add_column("风格")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("夏普", justify="right")
    table.add_column("卡玛", justify="right")
    for row in payload["rank_table"]:
        table.add_row(
            str(row["rank"]),
            row["style_name"],
            f"{row['total_return']:.2%}",
            f"{row['max_drawdown']:.2%}",
            f"{row['sharpe']:.2f}",
            f"{row['calmar']:.2f}",
        )
    console.print(table)


@style_app.command("history")
def style_history_command(
    limit: int = typer.Option(20, "--limit", callback=_validate_limit, help="显示最近 N 条回测记录"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """查询风格回测历史。"""
    rows = list_style_backtest_results(limit=limit, settings=Settings())
    if output == "json":
        typer.echo(json.dumps([r.to_dict() for r in rows], ensure_ascii=False, indent=2))
        return
    if not rows:
        console.print("[yellow]暂无风格回测记录。[/yellow]")
        return

    table = Table(title="风格回测历史", box=box.SIMPLE)
    table.add_column("编号", justify="right")
    table.add_column("运行ID")
    table.add_column("回测时间")
    table.add_column("排序键")
    table.add_column("风格数", justify="right")
    table.add_column("落库时间")
    for row in rows:
        table.add_row(
            str(row.id),
            row.run_id,
            row.as_of,
            row.sort_key,
            str(row.styles_count),
            row.created_at,
        )
    console.print(table)


@style_app.command("show")
def style_show_command(
    record_id: int = typer.Argument(..., help="风格回测记录 ID"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """按记录 ID 查看单条风格回测结果。"""
    try:
        payload = get_style_backtest_result(record_id=record_id, settings=Settings())
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title=f"风格回测详情 #{payload['id']}", box=box.SIMPLE)
    table.add_column("排名", justify="right")
    table.add_column("风格")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("夏普", justify="right")
    table.add_column("卡玛", justify="right")
    for row in payload["rank_table"]:
        table.add_row(
            str(row["rank"]),
            row["style_name"],
            f"{row['total_return']:.2%}",
            f"{row['max_drawdown']:.2%}",
            f"{row['sharpe']:.2f}",
            f"{row['calmar']:.2f}",
        )
    console.print(table)


@context_app.command("daily")
def context_daily_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON schema 后退出"),
    strict_source: str = typer.Option("latest", "--strict-source", callback=_validate_strict_source),
    max_age_hours: int = typer.Option(24, "--max-age-hours", callback=_validate_positive_hours),
    strict_window: str = typer.Option("all", "--strict-window", callback=_validate_strict_window),
    windows: str = typer.Option(
        "24,7,30",
        "--windows",
        help="交易窗口列表（逗号分隔正整数，如 24,7,30）",
    ),
) -> None:
    """聚合每日 Agent 决策上下文（仅输出数据，不做推荐）。"""
    if json_schema:
        _print_json_schema("context.daily")
        return

    started = perf_counter()
    app_settings = Settings()

    signal_rows = list_signal_snapshots(limit=1, settings=app_settings)
    if not signal_rows:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            context="context.daily",
            message="缺少 signal 快照历史，请先执行 signal snapshot。",
            details={
                "strict_mode": True,
                "missing_component": "signal_latest",
            },
            hint={"action": "run_signal_snapshot"},
            output=output,
        )
        return

    style_rows = list_style_backtest_results(limit=1, settings=app_settings)
    if not style_rows:
        _emit_strict_failure(
            code=ErrorCode.STYLE_EVAL_FAILED,
            context="context.daily",
            message="缺少 style 回测历史，请先执行 style backtest-rank。",
            details={
                "strict_mode": True,
                "missing_component": "style_latest",
            },
            hint={"action": "run_style_backtest_rank"},
            output=output,
        )
        return

    signal_age = _calc_age_hours(signal_rows[0].as_of)
    style_age = _calc_age_hours(style_rows[0].as_of)
    source_meta = {
        "strict_source": strict_source,
        "max_age_hours": max_age_hours,
        "signal_latest": {
            "record_id": signal_rows[0].id,
            "snapshot_id": signal_rows[0].snapshot_id,
            "as_of": signal_rows[0].as_of,
            "age_hours": round(signal_age, 6) if signal_age is not None else None,
        },
        "style_latest": {
            "record_id": style_rows[0].id,
            "run_id": style_rows[0].run_id,
            "as_of": style_rows[0].as_of,
            "age_hours": round(style_age, 6) if style_age is not None else None,
        },
    }

    if strict_source == "fresh":
        stale_components: list[dict] = []
        for component, meta in (
            ("signal_latest", source_meta["signal_latest"]),
            ("style_latest", source_meta["style_latest"]),
        ):
            age_hours = meta["age_hours"]
            if age_hours is None or age_hours > max_age_hours:
                stale_components.append(
                    {
                        "component": component,
                        "as_of": meta["as_of"],
                        "age_hours": age_hours,
                    }
                )
        if stale_components:
            _emit_strict_failure(
                code=ErrorCode.PIPELINE_ABORTED_STRICT,
                context="context.daily",
                message="上下文快照已过期，严格模式中断。",
                details={
                    "strict_mode": True,
                    "strict_source": strict_source,
                    "max_age_hours": max_age_hours,
                    "stale_components": stale_components,
                },
                hint={"action": "refresh_signal_and_style"},
                output=output,
            )
            return

    positions, bars_by_symbol = _load_check_data(app_settings)
    check_result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)
    current = show_current_strategy().current_strategy
    drift_items = analyze_positions_drift(strategy_name=current)

    payload = {
        "as_of": signal_rows[0].as_of,
        "decision_boundary": _decision_boundary_meta(),
        "check": {
            "verdict": check_result.verdict,
            "summary": check_result.verdict_summary,
            "has_no_history": check_result.has_no_history,
            "signals": [
                {
                    "symbol": s.symbol,
                    "max_drawdown_7d_pct": round(s.max_drawdown_7d * 100, 2),
                    "alert_level": s.alert_level.value,
                    "action_hint": s.action_hint,
                }
                for s in check_result.signals
            ],
        },
        "drift": {
            "strategy": current,
            "count": len(drift_items),
            "items": [item.to_dict() for item in drift_items],
        },
        "source_meta": source_meta,
        "signal_latest": get_signal_snapshot(record_id=signal_rows[0].id, settings=app_settings),
        "style_latest": get_style_backtest_result(record_id=style_rows[0].id, settings=app_settings),
    }

    window_sizes = _parse_windows(windows)

    windows_payload: dict[str, dict] = {}
    window_failures: list[dict] = []
    for size in window_sizes:
        window_key = f"w{size}"
        try:
            win_signal = build_signal_snapshot(settings=app_settings, window_bars=size)
        except SignalPipelineError as exc:
            failure = {
                "window_key": window_key,
                "component": "signal",
                "reason": exc.message,
                "details": exc.details,
            }
            window_failures.append(failure)
            if strict_window == "all":
                continue
            windows_payload[window_key] = {
                "window_size": size,
                "status": "failed",
                "error": failure,
            }
            continue
        try:
            win_style = run_style_backtest_rank(settings=app_settings, window_bars=size)
        except StyleBacktestError as exc:
            failure = {
                "window_key": window_key,
                "component": "style",
                "reason": exc.message,
                "details": exc.details,
            }
            window_failures.append(failure)
            if strict_window == "all":
                continue
            windows_payload[window_key] = {
                "window_size": size,
                "status": "failed",
                "error": failure,
            }
            continue
        windows_payload[window_key] = {
            "window_size": size,
            "status": "ok",
            "check": payload["check"],
            "drift": payload["drift"],
            "signal": win_signal,
            "style": win_style,
            "source_meta": {
                "window_key": window_key,
                "signal_as_of": win_signal.get("as_of"),
                "style_as_of": win_style.get("as_of"),
                "style_run_id": win_style.get("run_id"),
            },
        }

    if strict_window == "all" and window_failures:
        _emit_strict_failure(
            code=ErrorCode.PIPELINE_ABORTED_STRICT,
            context="context.daily",
            message="窗口计算失败，严格模式中断。",
            details={
                "strict_mode": True,
                "strict_window": strict_window,
                "windows_requested": list(window_sizes),
                "window_count_requested": len(window_sizes),
                "window_failures": window_failures,
            },
            hint={"action": "fix_window_pipeline"},
            output=output,
        )
        return

    success_count = sum(
        1 for item in windows_payload.values()
        if isinstance(item, dict) and item.get("status") == "ok"
    )
    failed_count = len(window_failures)
    ok_windows = {
        key: item for key, item in windows_payload.items()
        if isinstance(item, dict) and item.get("status") == "ok"
    }

    signal_states_by_key: dict[str, dict[str, str]] = {}
    for window_key, item in ok_windows.items():
        for signal in item["signal"]["signals"]:
            signal_key = signal["signal_key"]
            signal_states_by_key.setdefault(signal_key, {})[window_key] = signal["state"]

    signal_conflicts: list[dict] = []
    for signal_key, states_by_window in signal_states_by_key.items():
        if len(set(states_by_window.values())) > 1:
            signal_conflicts.append(
                {
                    "signal_key": signal_key,
                    "states_by_window": states_by_window,
                }
            )

    top_style_by_window = {
        window_key: (
            item["style"]["rank_table"][0]["style_name"]
            if item["style"].get("rank_table")
            else None
        )
        for window_key, item in ok_windows.items()
    }
    unique_top_styles = {v for v in top_style_by_window.values() if v is not None}

    verdict_by_window = {
        window_key: item["check"]["verdict"]
        for window_key, item in ok_windows.items()
    }
    unique_verdicts = set(verdict_by_window.values())

    total_signals_compared = len(signal_states_by_key)
    signal_consensus = (
        1.0
        if total_signals_compared == 0
        else max(0.0, 1.0 - (len(signal_conflicts) / total_signals_compared))
    )
    style_consensus = 1.0 if len(unique_top_styles) <= 1 else 0.0
    risk_consensus = 1.0 if len(unique_verdicts) <= 1 else 0.0

    payload["windows"] = windows_payload
    payload["window_diff"] = {
        "signal_diff": {
            "total_signals_compared": total_signals_compared,
            "conflict_count": len(signal_conflicts),
            "conflicts": signal_conflicts,
        },
        "style_diff": {
            "top_style_by_window": top_style_by_window,
            "unique_top_style_count": len(unique_top_styles),
            "is_conflict": len(unique_top_styles) > 1,
        },
        "risk_diff": {
            "verdict_by_window": verdict_by_window,
            "unique_verdict_count": len(unique_verdicts),
            "is_conflict": len(unique_verdicts) > 1,
        },
        "consensus_score": round((signal_consensus + style_consensus + risk_consensus) / 3, 6),
    }
    payload["summary"] = {
        "latency_ms": round((perf_counter() - started) * 1000, 3),
        "windows_requested": list(window_sizes),
        "window_count_requested": len(window_sizes),
        "window_count_success": success_count,
        "window_count_failed": failed_count,
        "window_failures": window_failures,
    }

    if output == "json":
        _print_json(payload=payload, command="context.daily", envelope=envelope)
        return

    console.print(f"[bold]每日上下文[/bold] as_of={payload['as_of']}")
    console.print(f"健康结论：{payload['check']['summary']}")
    console.print(f"持仓偏离条目：{payload['drift']['count']}")
    console.print(
        "最新快照："
        f" signal={payload['signal_latest']['snapshot_id']} "
        f"style={payload['style_latest']['run_id']}"
    )


@app.callback()
def main(
    database_url: str | None = typer.Option(None, "--database-url", hidden=True, help="覆盖数据库 URL"),
) -> None:
    """HiveFlow CLI 主入口。"""
    import os
    if database_url is not None:
        os.environ["HIVEFLOW_DATABASE_URL"] = database_url


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

    grid_positions = list_grid_positions()

    if not positions and not grid_positions:
        if output_format == "json":
            typer.echo('{"free": [], "grid": []}')
        else:
            typer.echo("暂无持仓记录。")
        return

    if output_format == "json":
        payload = {
            "free": [position.to_dict() for position in positions],
            "grid": [g.to_dict() for g in grid_positions],
        }
        _print_json(payload=payload, command="positions.list", envelope=envelope)
        return

    # --- 自由持仓 ---
    if ui_theme == "minimal":
        console.print(":: 自由持仓 ::")
        free_table = Table(
            show_lines=False,
            box=box.SIMPLE,
        )
        free_table.add_column("标的", justify="left")
        free_table.add_column("数量", justify="right")
        free_table.add_column("市值", justify="right")
        free_table.add_column("权重", justify="right")
    else:
        console.print("[bold #5fd75f]:: 自由持仓 ::[/bold #5fd75f]")
        free_table = Table(
            show_lines=False,
            header_style="bold #5f875f",
            border_style="#5f875f",
            box=box.SIMPLE_HEAVY,
        )
        free_table.add_column("标的", justify="left", style="#87ff87")
        free_table.add_column("数量", justify="right", style="#5f875f")
        free_table.add_column("市值", justify="right", style="#5f875f")
        free_table.add_column("权重", justify="right", style="#5f875f")

    for position in positions:
        free_table.add_row(
            position.symbol,
            f"{position.quantity:.6f}",
            f"{position.market_value:.2f}",
            f"{position.weight:.2%}",
        )
    console.print(free_table)

    # --- 网格持仓 ---
    if grid_positions:
        if ui_theme == "minimal":
            console.print(":: 网格持仓（不参与调仓计算）::")
            grid_table = Table(
                show_lines=False,
                box=box.SIMPLE,
            )
            grid_table.add_column("标的", justify="left")
            grid_table.add_column("类型", justify="left")
            grid_table.add_column("基础资产", justify="right")
            grid_table.add_column("稳定币数量", justify="right")
            grid_table.add_column("网格 ID", justify="left")
            grid_table.add_column("交易对", justify="left")
            grid_table.add_column("状态", justify="left")
        else:
            console.print("[bold #5fd75f]:: 网格持仓（不参与调仓计算）::[/bold #5fd75f]")
            grid_table = Table(
                show_lines=False,
                header_style="bold #5f875f",
                border_style="#5f875f",
                box=box.SIMPLE_HEAVY,
            )
            grid_table.add_column("标的", justify="left", style="#87ff87")
            grid_table.add_column("类型", justify="left", style="#5f875f")
            grid_table.add_column("基础资产", justify="right", style="#5f875f")
            grid_table.add_column("稳定币数量", justify="right", style="#5f875f")
            grid_table.add_column("网格 ID", justify="left", style="#5f875f")
            grid_table.add_column("交易对", justify="left", style="#5f875f")
            grid_table.add_column("状态", justify="left", style="#5f875f")

        for g in grid_positions:
            grid_table.add_row(
                g.symbol,
                g.inst_type,
                f"{g.base_quantity:.6f}",
                f"{g.quote_quantity:.2f}",
                g.grid_id,
                g.inst_id,
                g.state,
            )
        console.print(grid_table)


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


@targets_app.command("set-from-backtest")
def targets_set_from_backtest_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID（来自 backtest list）"),
) -> None:
    """将回测结果的配比设为当前目标配比。"""
    from hiveflow.application.backtest import set_targets_from_backtest
    try:
        weights = set_targets_from_backtest(backtest_id=backtest_id)
    except ValueError as e:
        console.print(f"[bold red]错误：{e}[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold green]已设置目标配比（来自回测 #{backtest_id}）：[/bold green]")
    for symbol, weight in sorted(weights.items()):
        console.print(f"  {symbol}  {weight:.0%}")


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
    file: Path | None = typer.Option(None, "--file", "-f", help="行情 CSV（不填则从 DB 读）"),
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
            settings=Settings(),
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
    table.add_column("编号", justify="right")
    table.add_column("策略", justify="left")
    table.add_column("类型")
    table.add_column("周期", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("夏普比率", justify="right")
    table.add_column("时间", justify="left")
    for item in rows:
        table.add_row(
            str(item.id) if item.id is not None else "-",
            item.strategy_name,
            item.backtest_type,
            str(item.periods),
            f"{item.total_return:.2%}",
            f"{item.max_drawdown:.2%}",
            f"{item.sharpe:.2f}",
            item.created_at,
        )
    console.print(table)


@backtest_app.command("show")
def backtest_show_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """展示单条回测的权益曲线与指标汇总。"""
    import math
    output_format = _validate_output_format(output)
    try:
        result = get_backtest_result(backtest_id, settings=Settings())
    except ValueError as exc:
        typer.echo(f"错误：{exc}")
        raise typer.Exit(code=1)

    if output_format == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    backtest_type_label = "动态" if result.backtest_type == "dynamic" else "静态"
    typer.echo(
        f"回测 #{result.id} · {result.strategy_name} · {backtest_type_label} · {result.periods} 天"
    )
    typer.echo("")
    typer.echo(f"  总收益     最大回撤    Sharpe")
    typer.echo(
        f"  {result.total_return:+.1%}    {result.max_drawdown:.1%}       {result.sharpe:.2f}"
    )
    typer.echo("")
    if result.equity_curve is None:
        typer.echo("  权益曲线")
        typer.echo("  [历史记录无曲线数据，重新运行回测可获得曲线]")
    else:
        curve = json.loads(result.equity_curve)
        spark = _sparkline(curve, width=40)
        typer.echo(f"  权益曲线（{result.periods} 期）")
        typer.echo(f"  {spark}")
        created_date = result.created_at[:10]
        typer.echo(f"  创建：{created_date}")
        # 风险指标节（从 equity curve 派生）
        try:
            risk = analyze_portfolio_risk(result.id, settings=Settings())
        except ValueError:
            risk = None
        if risk is not None:
            typer.echo("")
            typer.echo("  风险指标")
            typer.echo(f"  年化波动率   {risk['annual_vol']:.1%}")
            typer.echo(f"  胜率         {risk['win_rate']:.1%}")
            calmar_str = f"{risk['calmar_ratio']:.2f}" if not math.isinf(risk["calmar_ratio"]) else "∞"
            typer.echo(f"  Calmar       {calmar_str}")


@backtest_app.command("compare")
def backtest_compare_command(
    ids: list[int] = typer.Argument(..., help="回测记录 ID 列表（空格分隔）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """并排对比多条回测的权益曲线与指标。"""
    output_format = _validate_output_format(output)

    # 全量预检：先收集所有无效 ID，再输出
    settings = Settings()
    errors: list[str] = []
    results: list[BacktestResultView] = []
    for bid in ids:
        try:
            results.append(get_backtest_result(bid, settings=settings))
        except ValueError:
            errors.append(str(bid))
    if errors:
        typer.echo(f"错误：以下回测记录不存在：{', '.join(errors)}")
        raise typer.Exit(code=1)

    if output_format == "json":
        typer.echo(json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2))
        return

    # 指标对比表
    typer.echo("策略对比\n")
    typer.echo(f"  {'ID':>4}  {'策略':<16}  {'类型':<6}  {'周期':>4}  {'总收益':>8}  {'最大回撤':>8}  {'Sharpe':>6}")
    for r in results:
        btype = "动态" if r.backtest_type == "dynamic" else "静态"
        typer.echo(
            f"  {r.id!s:>4}  {r.strategy_name:<16}  {btype:<6}  {r.periods:>4}  "
            f"{r.total_return:>+8.1%}  {r.max_drawdown:>8.1%}  {r.sharpe:>6.2f}"
        )

    # 权益曲线（各起点归一为 1.0，sparkline width=28）
    typer.echo("\n  权益曲线（各起点归一为 1.0）")
    for r in results:
        name = r.strategy_name[:14]
        if r.equity_curve is not None:
            curve = json.loads(r.equity_curve)
            spark = _sparkline(curve, width=28)
        else:
            spark = "[无曲线数据]"
        typer.echo(f"  #{r.id}  {name:<14}  {spark}")


@backtest_app.command("quant-run")
def backtest_quant_run_command(
    strategy: str = typer.Option(..., "--strategy", "-s", help="量化策略类名（如 MomentumStrategy）"),
    rebalance_days: int = typer.Option(7, "--rebalance-days", help="再平衡周期（天，默认 7）"),
    symbols: str | None = typer.Option(None, "--symbols", help="资产池，逗号分隔（不填则用 MarketBar 全部）"),
    fee_bps: float = typer.Option(0.0, "--fee-bps", help="单次再平衡手续费（基点）"),
    slippage_bps: float = typer.Option(0.0, "--slippage-bps", help="单次再平衡滑点（基点）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """运行量化策略动态回测（每隔 N 天重新计算权重）。"""
    from hiveflow.application.backtest import run_quant_backtest

    output_format = _validate_output_format(output)

    # 解析策略类
    if strategy not in _BUILTIN_STRATEGIES:
        console.print(f"[red]未知策略：{strategy}，可用策略请运行 'hiveflow quant list'[/red]")
        raise typer.Exit(1)
    strategy_class, _ = _BUILTIN_STRATEGIES[strategy]
    strategy_instance = strategy_class()

    # 解析 symbols
    symbols_list: list[str] | None = None
    if symbols:
        symbols_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]

    try:
        result = run_quant_backtest(
            strategy=strategy_instance,
            rebalance_days=rebalance_days,
            symbols=symbols_list,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
    except ValueError as exc:
        console.print(f"[red]回测失败：{exc}[/red]")
        raise typer.Exit(1)

    if output_format == "json":
        payload = result.to_dict()
        payload["strategy"] = result.strategy_name  # 冗余字段方便 Agent 消费
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    table = Table(title="动态回测结果", show_lines=False, box=box.SIMPLE, min_width=80)
    table.add_column("策略", style="bold", no_wrap=True)
    table.add_column("类型")
    table.add_column("再平衡周期")
    table.add_column("总周期数", justify="right")
    table.add_column("总收益", justify="right")
    table.add_column("最大回撤", justify="right")
    table.add_column("夏普比率", justify="right")
    table.add_row(
        result.strategy_name,
        result.backtest_type,
        f"{rebalance_days} 天",
        str(result.periods),
        f"{result.total_return:.2%}",
        f"{result.max_drawdown:.2%}",
        f"{result.sharpe:.2f}",
    )
    console.print(table)
    console.print(f"[dim]回测 ID：{result.id}（可用 'hiveflow targets set-from-backtest {result.id}' 应用）[/dim]")


@app.command()
def sync(
    days: int | None = typer.Option(None, "--days", help="同步最近 N 天 K 线（超过 100 天自动分页）"),
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
    if days is not None and not (1 <= days <= 500):
        console.print("错误：--days 必须在 1 到 500 之间。", style="bold red")
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
    """输出持仓风险健康数据（退出码始终为 0）。"""
    settings = Settings()
    positions, bars_by_symbol = _load_check_data(settings)
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)

    if output == "json":
        payload = {
            "decision_boundary": _decision_boundary_meta(),
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
        console.print("[yellow]提示：未检测到历史行情数据，请先执行 hiveflow sync --days 30 以启用风险数据输出。[/yellow]")
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


@trade_app.command("execute")
def trade_execute_command(
    orders_json: str = typer.Option(..., "--orders", help='订单列表 JSON，格式：[{"symbol":"BTC","action":"buy","usdt":500}]'),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """执行现货市价单（需要 Trade 权限 API Key）。"""
    import json as _json
    settings = Settings()
    if not (settings.okx_trade_api_key and settings.okx_trade_api_secret and settings.okx_trade_passphrase):
        console.print(
            "错误：未配置 OKX TRADE API Key。请在 .env 中设置：\n"
            "  HIVEFLOW_OKX_TRADE_API_KEY / _SECRET / _PASSPHRASE",
            style="bold red",
        )
        raise typer.Exit(code=1)

    try:
        raw = _json.loads(orders_json)
        orders = [TradeOrder(symbol=o["symbol"], action=o["action"], usdt=float(o["usdt"])) for o in raw]
    except Exception as e:
        console.print(f"[bold red]错误：订单 JSON 格式无效：{e}[/bold red]")
        raise typer.Exit(code=1)

    console.print("[bold]待执行订单：[/bold]")
    for o in orders:
        action_cn = "买入" if o.action == "buy" else "卖出"
        console.print(f"  {action_cn} {o.symbol}  {o.usdt:.2f} USDT（市价）")

    console.print()
    confirm = typer.prompt("输入 confirm 确认执行，其他任意内容取消")
    if confirm.strip().lower() != "confirm":
        console.print("已取消。")
        raise typer.Exit(code=0)

    console.print("\n执行中...")
    results = execute_trades(
        orders=orders,
        api_key=settings.okx_trade_api_key,
        api_secret=settings.okx_trade_api_secret,
        passphrase=settings.okx_trade_passphrase,
    )

    has_failure = False
    success_ids = []
    for r in results:
        action_cn = "买入" if r.order.action == "buy" else "卖出"
        if r.success:
            console.print(f"  ✅ {action_cn} {r.order.symbol}  {r.order.usdt:.2f} USDT → 订单 ID: {r.order_id}")
            success_ids.append(r.order_id)
        else:
            console.print(f"  ❌ {action_cn} {r.order.symbol}  {r.order.usdt:.2f} USDT → 失败：{r.error_msg}")
            has_failure = True

    if has_failure:
        console.print(f"\n[bold yellow]⚠️  部分订单失败，请在 OKX 手动确认账户状态。成功订单 ID：{', '.join(success_ids)}[/bold yellow]")
        raise typer.Exit(code=1)
    else:
        console.print("\n[bold green]执行完成。[/bold green]")


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
app.add_typer(trade_app, name="trade")
app.add_typer(skills_app, name="skills")
quant_app.add_typer(blend_app, name="blend")
app.add_typer(quant_app, name="quant")
app.add_typer(risk_analysis_app, name="risk-analysis")
app.add_typer(perf_app, name="perf")
app.add_typer(signal_app, name="signal")
app.add_typer(style_app, name="style")
app.add_typer(context_app, name="context")


@skills_app.command("list")
def skills_list_command(
    output: str = typer.Option("table", "--output", help="输出格式：table / json"),
) -> None:
    """列出项目内所有 skill 及其安装状态。"""
    skills_dir = get_skills_dir()
    target_dir = get_target_dir()
    skills = list_skills(skills_dir=skills_dir, target_dir=target_dir)

    if not skills:
        console.print(f"[yellow]未找到 skills（查找目录：{skills_dir}）[/yellow]")
        console.print("请确保在项目根目录运行，或设置 HIVEFLOW_SKILLS_DIR 环境变量。")
        return

    if output == "json":
        console.print(json.dumps([{
            "name": s.name,
            "installed": s.installed,
            "source": str(s.source),
            "target": str(s.target),
        } for s in skills], indent=2, ensure_ascii=False))
        return

    table = Table(
        title="Skills（技能包）",
        box=box.SIMPLE,
        show_header=True,
    )
    table.add_column("名称", justify="left")
    table.add_column("状态", justify="left")

    for s in skills:
        status = "[green]✓ 已安装[/green]" if s.installed else "[yellow]✗ 未安装[/yellow]"
        table.add_row(s.name, status)

    console.print(table)
    console.print(f"目标目录：{target_dir}")
    if any(not s.installed for s in skills):
        console.print("\n运行 'hiveflow skills install' 安装全部")


@skills_app.command("install")
def skills_install_command(
    name: str | None = typer.Argument(None, help="指定安装的 skill 名称，不填则安装全部"),
    force: bool = typer.Option(False, "--force", help="强制覆盖已存在的目录或错误软链接"),
) -> None:
    """将 skills/ 目录中的 skill 软链接到 ~/.agents/skills/。"""
    skills_dir = get_skills_dir()
    target_dir = get_target_dir()

    if not skills_dir.exists():
        console.print(f"[red]错误：未找到 skills 目录（{skills_dir}）[/red]")
        console.print("请确保在项目根目录运行，或设置 HIVEFLOW_SKILLS_DIR 环境变量。")
        raise typer.Exit(1)

    results = install_skills(name=name, skills_dir=skills_dir, target_dir=target_dir, force=force)

    if not results:
        console.print(f"[yellow]未找到 skill：{name}[/yellow]")
        raise typer.Exit(1)

    for skill_name, msg in results:
        if "warning" in msg.lower():
            console.print(f"  [yellow]⚠ {skill_name}[/yellow]：{msg}")
        elif "already" in msg.lower() or "skip" in msg.lower():
            console.print(f"  [dim]– {skill_name}：{msg}[/dim]")
        else:
            console.print(f"  [green]✓ {skill_name}[/green]：{msg}")


# ────────────── quant ──────────────

_BUILTIN_STRATEGIES: dict[str, tuple[type[BaseStrategy], str]] = {
    "EqualWeightStrategy": (EqualWeightStrategy, "等权重（基准策略）"),
    "MomentumStrategy": (MomentumStrategy, "动量（按涨幅排名分配权重）"),
    "MeanReversionStrategy": (MeanReversionStrategy, "均值回归（z-score 反向加权）"),
    "MovingAverageCrossStrategy": (MovingAverageCrossStrategy, "均线交叉（短期均线在长期均线上方加权）"),
    "BollingerBandStrategy": (BollingerBandStrategy, "布林带（超卖区域加权）"),
    "RiskParityStrategy": (RiskParityStrategy, "风险平价（按波动率倒数分配）"),
    "MaxSharpeStrategy": (MaxSharpeStrategy, "最大夏普（需 PyPortfolioOpt）"),
    "MinVarianceStrategy": (MinVarianceStrategy, "最小方差（需 PyPortfolioOpt）"),
}


def _coerce_param(value: str) -> int | float | str:
    """推导 --param 值类型：先 int，再 float，失败保留 str。"""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


@quant_app.command("list")
def quant_list_command():
    """列出所有可用量化策略（内置 + 用户配置）。"""
    table = Table(title="量化策略", box=box.SIMPLE)
    table.add_column("名称", style="bold")
    table.add_column("类型")
    table.add_column("描述")
    for name, (_, desc) in _BUILTIN_STRATEGIES.items():
        table.add_row(name, "内置", desc)

    import os
    env_file = os.environ.get("HIVEFLOW_STRATEGY_FILE")
    env_class = os.environ.get("HIVEFLOW_STRATEGY_CLASS")
    if env_file and env_class:
        table.add_row(env_class, "用户自定义", env_file)

    console.print(table)
    console.print()
    console.print("用法：hiveflow quant run --strategy <名称>")
    console.print("自定义策略：hiveflow quant run --strategy-file <路径> --strategy <类名>")


@quant_app.command("run")
def quant_run_command(
    strategy: str = typer.Option(..., "--strategy", help="策略类名（内置或自定义）"),
    strategy_file: str | None = typer.Option(None, "--strategy-file", help="用户自定义策略文件路径"),
    param: list[str] = typer.Option([], "--param", help="策略参数 key=value（可多次使用）"),
    apply: bool = typer.Option(False, "--apply", help="写入目标配比（replace 模式）"),
    output: str = typer.Option("table", "--output", help="输出格式：table / json"),
):
    """运行量化策略，输出权重信号。"""
    settings = Settings()

    parsed_params: dict[str, int | float | str] = {}
    for p in param:
        if "=" not in p:
            console.print(f"[red]无效参数格式：{p}（应为 key=value）[/red]")
            raise typer.Exit(1)
        key, val = p.split("=", 1)
        parsed_params[key.strip()] = _coerce_param(val.strip())

    strategy_class: type[BaseStrategy] | None = None
    file_path: str | None = strategy_file

    import os
    if file_path is None and os.environ.get("HIVEFLOW_STRATEGY_FILE"):
        file_path = os.environ.get("HIVEFLOW_STRATEGY_FILE")

    if file_path:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_user_strategy", file_path)
        if spec is None or spec.loader is None:
            console.print(f"[red]无法加载文件：{file_path}[/red]")
            raise typer.Exit(1)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        strategy_class = getattr(module, strategy, None)
        if strategy_class is None:
            console.print(f"[red]文件 {file_path} 中未找到类 {strategy}[/red]")
            raise typer.Exit(1)
    elif strategy in _BUILTIN_STRATEGIES:
        strategy_class, _ = _BUILTIN_STRATEGIES[strategy]
    else:
        console.print(f"[red]未知策略：{strategy}，可用策略请运行 'hiveflow quant list'[/red]")
        raise typer.Exit(1)

    try:
        result = run_quant_strategy(
            strategy_class=strategy_class,
            strategy_file=file_path,
            params=parsed_params,
            apply=apply,
            settings=settings,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    table = Table(title=f"策略运行结果：{result.strategy_name}", box=box.SIMPLE)
    table.add_column("资产", style="bold")
    table.add_column("权重", justify="right")
    for sym, w in sorted(result.weights.items(), key=lambda x: x[1], reverse=True):
        table.add_row(sym, f"{w:.2%}")
    console.print(table)
    console.print(f"[dim]运行 ID：{result.run_id} | 时间：{result.run_at}[/dim]")
    if apply:
        console.print("[green]已写入目标配比（TargetAllocation）。[/green]")


@quant_app.command("history")
def quant_history_command(
    limit: int = typer.Option(10, "--limit", help="显示最近 N 条记录"),
    run_id: int | None = typer.Option(None, "--id", help="查询指定运行 ID"),
    output: str = typer.Option("table", "--output", help="输出格式：table / json"),
):
    """查看量化策略运行历史。"""
    settings = Settings()
    runs = list_strategy_runs(limit=limit, run_id=run_id, settings=settings)

    if not runs:
        console.print("[dim]暂无运行记录。[/dim]")
        return

    if output == "json":
        if run_id is not None and len(runs) == 1:
            console.print(json.dumps(runs[0].to_dict(), ensure_ascii=False, indent=2))
        else:
            console.print(json.dumps([r.to_dict() for r in runs], ensure_ascii=False, indent=2))
        return

    table = Table(title="策略运行历史", box=box.SIMPLE)
    table.add_column("编号", style="bold")
    table.add_column("策略名称")
    table.add_column("参数")
    table.add_column("已写入")
    table.add_column("运行时间")
    for r in runs:
        table.add_row(
            str(r.id),
            r.strategy_name,
            str(r.params),
            "✓" if r.applied else "-",
            r.run_at,
        )
    console.print(table)


@blend_app.command("create")
def blend_create(
    name: str = typer.Argument(..., help="Blend 配置名称（唯一）"),
    strategies: str = typer.Option(..., "--strategies", help="逗号分隔的策略名称，如 MomentumStrategy,EqualWeightStrategy"),
    weights: str | None = typer.Option(None, "--weights", help="逗号分隔的手动权重（可选），如 0.6,0.4"),
    optimize_metric: str = typer.Option("sharpe", "--optimize-metric", help="自动优化指标：sharpe | calmar | return"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """创建多策略混合配置。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    strategy_list = [s.strip() for s in strategies.split(",")]
    weight_list = [float(w.strip()) for w in weights.split(",")] if weights else None
    try:
        cfg = create_blend(
            name=name,
            strategy_names=strategy_list,
            weights=weight_list,
            optimize_metric=optimize_metric,
            settings=settings,
        )
    except ValueError as e:
        console.print(f"[red]错误：{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Blend 配置 '{cfg.name}' 已创建（auto_optimized={cfg.auto_optimized}）[/green]")


@blend_app.command("list")
def blend_list(
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """列出所有 blend 配置。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    blends = list_blends(settings=settings)
    if output == "json":
        typer.echo(json.dumps([b.to_dict() for b in blends], ensure_ascii=False))
        return
    if not blends:
        console.print("[yellow]暂无 blend 配置。[/yellow]")
        return
    table = Table(title="Blend 配置列表", box=box.SIMPLE)
    table.add_column("编号", style="dim")
    table.add_column("名称", style="bold")
    table.add_column("策略", style="cyan")
    table.add_column("自动优化")
    table.add_column("指标")
    table.add_column("更新时间", style="dim")
    for b in blends:
        table.add_row(
            str(b.id),
            b.name,
            ", ".join(b.strategy_names),
            "✓" if b.auto_optimized else "手动",
            b.optimize_metric,
            b.updated_at[:19],
        )
    console.print(table)


@blend_app.command("show")
def blend_show(
    name: str = typer.Argument(..., help="Blend 配置名称"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """显示 blend 配置详情。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        cfg = get_blend(name=name, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if output == "json":
        typer.echo(json.dumps(cfg.to_dict(), ensure_ascii=False))
        return
    console.print(Panel(
        f"[bold]{cfg.name}[/bold]\n"
        f"策略：{', '.join(cfg.strategy_names)}\n"
        f"自动优化：{'是' if cfg.auto_optimized else '否'}（指标：{cfg.optimize_metric}）\n"
        f"当前权重：{json.dumps(cfg.weights, ensure_ascii=False)}\n"
        f"创建：{cfg.created_at[:19]}  更新：{cfg.updated_at[:19]}",
        title="Blend 配置",
    ))


@blend_app.command("run")
def blend_run(
    name: str = typer.Argument(..., help="Blend 配置名称"),
    apply: bool = typer.Option(False, "--apply", help="写入 TargetAllocation"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """执行 blend：计算混合后资产权重，可选写入目标配比。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        result = run_blend(name=name, apply=apply, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if output == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False))
        return
    table = Table(title=f"Blend '{result.name}' 资产权重", box=box.SIMPLE)
    table.add_column("资产", style="bold")
    table.add_column("权重", style="cyan")
    for symbol, w in sorted(result.asset_weights.items(), key=lambda x: -x[1]):
        table.add_row(symbol, f"{w:.4f}")
    console.print(table)
    if result.applied:
        console.print("[green]已写入 TargetAllocation[/green]")


@blend_app.command("update")
def blend_update(
    name: str = typer.Argument(..., help="要覆盖的 Blend 配置名称"),
    strategies: str = typer.Option(..., "--strategies", help="新的逗号分隔策略名称"),
    weights: str | None = typer.Option(None, "--weights", help="新的逗号分隔手动权重（可选）"),
    optimize_metric: str = typer.Option("sharpe", "--optimize-metric", help="自动优化指标：sharpe | calmar | return"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """覆盖更新 blend 配置（策略、权重、优化指标）。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    strategy_list = [s.strip() for s in strategies.split(",")]
    weight_list = [float(w.strip()) for w in weights.split(",")] if weights else None
    try:
        cfg = update_blend(
            name=name,
            strategy_names=strategy_list,
            weights=weight_list,
            optimize_metric=optimize_metric,
            settings=settings,
        )
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Blend 配置 '{cfg.name}' 已更新（auto_optimized={cfg.auto_optimized}）[/green]")


@blend_app.command("delete")
def blend_delete(
    name: str = typer.Argument(..., help="要删除的 Blend 配置名称"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认提示"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """删除 blend 配置。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    if not yes:
        confirm = typer.confirm(f"确认删除 Blend 配置 '{name}'？")
        if not confirm:
            console.print("[yellow]已取消。[/yellow]")
            raise typer.Exit(0)
    try:
        delete_blend(name=name, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Blend 配置 '{name}' 已删除。[/green]")


@risk_analysis_app.command("assets")
def risk_assets_command(
    symbols: str | None = typer.Option(None, "--symbols", help="资产列表，逗号分隔（不填则用 MarketBar 全部）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """输出各资产年化波动率、历史最大回撤与相关性矩阵数据。"""
    import math
    output_format = _validate_output_format(output)
    symbols_list = (
        [s.strip().upper() for s in symbols.split(",") if s.strip()]
        if symbols
        else None
    )
    try:
        asset_views, corr_view = analyze_asset_risk(symbols=symbols_list, settings=Settings())
    except ValueError as exc:
        typer.echo(f"错误：{exc}")
        raise typer.Exit(code=1)

    if output_format == "json":
        payload = {
            "decision_boundary": _decision_boundary_meta(),
            "assets": [
                {
                    "symbol": v.symbol,
                    "annual_vol": round(v.annual_vol, 6),
                    "daily_vol": round(v.daily_vol, 6),
                    "max_drawdown": round(v.max_drawdown, 6),
                    "periods": v.periods,
                }
                for v in asset_views
            ],
            "correlation": {
                "symbols": corr_view.symbols,
                "matrix": [
                    [
                        round(val, 4) if not math.isnan(val) else None
                        for val in row
                    ]
                    for row in corr_view.matrix
                ],
            },
        }
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    typer.echo("资产风险数据\n")
    tbl = Table(show_lines=False, box=box.SIMPLE)
    tbl.add_column("资产")
    tbl.add_column("年化波动率", justify="right")
    tbl.add_column("日波动率", justify="right")
    tbl.add_column("历史 MDD", justify="right")
    tbl.add_column("数据点", justify="right")
    for v in asset_views:
        tbl.add_row(
            v.symbol,
            f"{v.annual_vol:.1%}",
            f"{v.daily_vol:.2%}",
            f"{v.max_drawdown:.1%}",
            str(v.periods),
        )
    console.print(tbl)

    typer.echo("\n  相关性矩阵")
    header = "        " + "  ".join(f"{s:>6}" for s in corr_view.symbols)
    typer.echo(header)
    for i, row in enumerate(corr_view.matrix):
        row_str = f"  {corr_view.symbols[i]:>5}  " + "  ".join(
            f"{val:>6.2f}" if not math.isnan(val) else "   N/A"
            for val in row
        )
        typer.echo(row_str)


@risk_analysis_app.command("portfolio")
def risk_portfolio_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从回测 equity curve 输出组合年化波动率、胜率与 Calmar ratio 数据。"""
    import math
    output_format = _validate_output_format(output)
    try:
        risk = analyze_portfolio_risk(backtest_id, settings=Settings())
    except ValueError as exc:
        typer.echo(f"错误：{exc}")
        raise typer.Exit(code=1)

    if risk is None:
        typer.echo("  [历史记录无曲线数据，重新运行回测可获得组合风险数据]")
        return

    if output_format == "json":
        serialized = {
            k: (None if isinstance(v, float) and (math.isinf(v) or math.isnan(v)) else v)
            for k, v in risk.items()
        }
        serialized["decision_boundary"] = _decision_boundary_meta()
        typer.echo(json.dumps(serialized, ensure_ascii=False, indent=2))
        return

    typer.echo(f"组合风险数据（回测 #{backtest_id}）\n")
    typer.echo(f"  年化波动率   {risk['annual_vol']:.1%}")
    typer.echo(f"  胜率         {risk['win_rate']:.1%}")
    calmar_str = f"{risk['calmar_ratio']:.2f}" if not math.isinf(risk["calmar_ratio"]) else "∞"
    typer.echo(f"  Calmar       {calmar_str}")


def take_perf_snapshot(
    api_key: str,
    api_secret: str,
    passphrase: str,
    source: str = "manual",
    settings: Settings | None = None,
) -> PortfolioSnapshotView:
    """从 OKX 获取最新持仓，计算总价值，存入快照。可 mock 用于测试。"""
    provider = OkxProvider(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
    positions = provider.fetch_positions()
    total_value = sum(p.market_value_usdt or 0.0 for p in positions)
    positions_data = {
        p.symbol: {"qty": p.quantity, "value_usd": p.market_value_usdt}
        for p in positions
    }
    return _record_snapshot_impl(
        total_value_usd=total_value,
        positions_data=positions_data,
        source=source,
        settings=settings,
    )


@perf_app.command("snapshot")
def perf_snapshot(
    source: str = typer.Option("manual", "--source", help="manual | cron"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """记录一次实盘组合快照（从 OKX 同步当前持仓价值）。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    api_key = settings.okx_api_key
    api_secret = settings.okx_api_secret
    passphrase = settings.okx_api_passphrase
    if not api_key or not api_secret or not passphrase:
        console.print(
            "[red]缺少 OKX 凭证，请设置 HIVEFLOW_OKX_API_KEY / "
            "HIVEFLOW_OKX_API_SECRET / HIVEFLOW_OKX_API_PASSPHRASE。[/red]"
        )
        raise typer.Exit(1)
    try:
        view = take_perf_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            source=source,
            settings=settings,
        )
    except Exception as e:
        console.print(f"[red]快照失败：{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]快照已记录：总价值 {view.total_value_usd:.2f} USD "
        f"（{view.timestamp[:19]}）[/green]"
    )


@perf_app.command("list")
def perf_list(
    limit: int = typer.Option(20, "--limit", help="最多显示条数"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """列出历史实盘快照。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    snaps = list_snapshots(limit=limit, settings=settings)
    if output == "json":
        typer.echo(json.dumps([s.to_dict() for s in snaps], ensure_ascii=False))
        return
    if not snaps:
        console.print("[yellow]暂无快照记录，请先运行 `hiveflow perf snapshot`。[/yellow]")
        return
    table = Table(title="实盘组合快照", box=box.SIMPLE)
    table.add_column("编号", style="dim")
    table.add_column("时间", style="bold")
    table.add_column("总价值（USD）", style="cyan")
    table.add_column("来源")
    table.add_column("备注", style="dim")
    for s in snaps:
        table.add_row(
            str(s.id),
            s.timestamp[:19],
            f"{s.total_value_usd:.2f}",
            s.source,
            s.notes or "",
        )
    console.print(table)


@perf_app.command("compare")
def perf_compare(
    backtest_id: int = typer.Argument(..., help="回测 ID"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """对比实盘权益曲线与指定回测，输出 Sparkline + 指标。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        result = compare_with_backtest(backtest_id=backtest_id, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False))
        return

    # Sparkline 并排
    console.print(f"\n[bold]实盘[/bold] ({result.snapshot_count} 个快照) vs [bold]回测 #{result.backtest_id}[/bold]\n")
    console.print(f"  实盘 : {result.live_sparkline}")
    console.print(f"  回测 : {result.backtest_sparkline}\n")

    # 指标表
    def _fmt_pct(v: float | None) -> str:
        return f"{v * 100:.2f}%" if v is not None else "N/A"

    table = Table(box=box.SIMPLE)
    table.add_column("指标", style="bold")
    table.add_column("实盘", style="cyan")
    table.add_column("回测", style="green")
    table.add_row("总收益率", _fmt_pct(result.live_total_return), _fmt_pct(result.backtest_total_return))
    table.add_row("年化收益率", _fmt_pct(result.live_annual_return), _fmt_pct(result.backtest_annual_return))
    table.add_row("最大回撤", _fmt_pct(result.live_mdd), _fmt_pct(result.backtest_mdd))
    console.print(table)


@perf_app.command("setup-cron")
def perf_setup_cron(
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印 crontab 行，不实际写入"),
    config_path: str = typer.Option("config/tracking.json", "--config", help="追踪配置文件路径"),
):
    """读取 config/tracking.json，安装 perf snapshot 定时任务到系统 crontab。"""
    import subprocess

    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]配置文件 {config_path} 不存在，请先创建 config/tracking.json。[/red]")
        raise typer.Exit(1)

    tracking_config = json.loads(config_file.read_text())
    interval = tracking_config.get("snapshot_interval", "1h")
    intervals = tracking_config.get("_intervals", {
        "1h": "0 * * * *",
        "6h": "0 */6 * * *",
        "daily": "0 9 * * *",
    })
    cron_schedule = intervals.get(interval, "0 * * * *")

    project_dir = Path.cwd().resolve()
    cron_line = f"{cron_schedule} cd {project_dir} && uv run hiveflow perf snapshot --source cron"

    if dry_run:
        console.print("[yellow]（dry-run）生成的 crontab 行：[/yellow]")
        console.print(cron_line)
        return

    # 读取现有 crontab，去重后追加
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_lines = existing.stdout.strip().splitlines() if existing.returncode == 0 else []
    # 移除旧的同类行
    current_lines = [line for line in current_lines if "hiveflow perf snapshot" not in line]
    current_lines.append(cron_line)
    new_crontab = "\n".join(current_lines) + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode != 0:
        console.print(f"[red]写入 crontab 失败：{proc.stderr}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]crontab 已更新（间隔：{interval}）：[/green]")
    console.print(cron_line)


def run() -> None:
    """CLI 入口函数，供 pyproject 脚本调用。"""
    app()


if __name__ == "__main__":
    run()
