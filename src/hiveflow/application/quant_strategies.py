"""量化策略应用服务：数据加载、策略运行、结果落库、--apply。"""
from __future__ import annotations

import json
from dataclasses import dataclass

import pandas as pd
from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.strategy_runs import StrategyRun
from hiveflow.services.strategies.base import BaseStrategy, StrategyContext


@dataclass(frozen=True)
class StrategyRunView:
    """策略运行历史视图。"""
    id: int | None
    strategy_name: str
    strategy_file: str | None
    params: dict
    weights: dict
    applied: bool
    run_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "strategy_file": self.strategy_file,
            "params": self.params,
            "weights": self.weights,
            "applied": self.applied,
            "run_at": self.run_at,
        }


@dataclass(frozen=True)
class QuantRunResult:
    """策略运行结果。"""
    run_id: int | None
    strategy_name: str
    params: dict
    weights: dict
    applied: bool
    run_at: str

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy_name,
            "params": self.params,
            "weights": self.weights,
            "run_id": self.run_id,
            "applied": self.applied,
            "run_at": self.run_at,
        }


def _build_prices(symbols: list[str], min_rows: int, settings: Settings) -> pd.DataFrame:
    """从 MarketBar 表构建 prices DataFrame (index=date, columns=symbol)。"""
    with get_session(settings) as session:
        bars = session.exec(
            select(MarketBar)
            .order_by(MarketBar.timestamp)
        ).all()

    # Python 层过滤 symbol（避免 .in_() 兼容性问题）
    if symbols:
        bars = [b for b in bars if b.symbol in set(symbols)]

    if not bars:
        raise ValueError(
            "MarketBar 表无数据，请先运行 `hiveflow market-data import` 导入行情数据。"
        )

    records = [{"symbol": b.symbol, "timestamp": b.timestamp, "close": b.close} for b in bars]
    df = pd.DataFrame(records)
    pivot = df.pivot_table(index="timestamp", columns="symbol", values="close")
    pivot.index = pd.to_datetime(pivot.index)
    pivot = pivot.sort_index()

    missing = [s for s in symbols if s not in pivot.columns and s != "USDT"]
    for s in missing:
        print(f"[警告] {s} 在 MarketBar 中无数据，已从权重计算中排除。")

    available = [s for s in symbols if s in pivot.columns]
    pivot = pivot[available]

    if len(pivot) < min_rows:
        raise ValueError(
            f"行情数据不足（需要 {min_rows} 行，实际 {len(pivot)} 行）。"
            "请运行 `hiveflow market-data import` 导入更多行情数据。"
        )

    return pivot


def _build_context(
    strategy_class: type[BaseStrategy],
    merged_params: dict,
    settings: Settings,
) -> StrategyContext:
    """构建 StrategyContext：加载 prices、positions、risk_signals。"""
    # 从 MarketBar 中获取去重 symbol 列表
    with get_session(settings) as session:
        all_bars = session.exec(select(MarketBar)).all()
    all_symbols = list({b.symbol for b in all_bars})
    if "USDT" not in all_symbols:
        all_symbols.append("USDT")

    # 确定加载行数
    window_keys = ("lookback_days", "window", "fast", "slow")
    windows = [int(merged_params.get(k, 0)) for k in window_keys if k in merged_params]
    max_window = max(windows) if windows else 30
    min_rows = max(max_window * 2, 60)

    prices = _build_prices(all_symbols, min_rows, settings)

    # 当前持仓（Position 使用 market_value 字段）
    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()
    total_value = sum(p.market_value or 0 for p in positions) or 1.0
    current_positions = {p.symbol: (p.market_value or 0) / total_value for p in positions}

    # 最新风险信号（RiskSignal 使用 calculated_at 字段）
    with get_session(settings) as session:
        risk_rows = session.exec(
            select(RiskSignal).order_by(RiskSignal.calculated_at.desc())
        ).all()
    risk_signals: dict = {}
    for r in risk_rows:
        if r.symbol not in risk_signals:
            risk_signals[r.symbol] = r

    return StrategyContext(
        prices=prices,
        current_positions=current_positions,
        risk_signals=risk_signals,
        params=merged_params,
    )


def _apply_weights(run: StrategyRun, weights: dict, settings: Settings) -> None:
    """写入 TargetAllocation（replace 模式），写 DecisionLog，更新 applied。"""
    with get_session(settings) as session:
        # 清除同策略旧记录
        session.exec(
            delete(TargetAllocation).where(
                TargetAllocation.strategy_name == run.strategy_name
            )
        )
        # 写入新权重
        for symbol, weight in weights.items():
            ta = TargetAllocation(
                symbol=symbol,
                target_weight=weight,
                strategy_name=run.strategy_name,
            )
            session.add(ta)
        # DecisionLog（使用 summary 字段，不是 content）
        log = DecisionLog(
            decision_type="quant-run-apply",
            summary=f"quant run --apply: {run.strategy_name} → {json.dumps(weights)}",
        )
        session.add(log)
        # 更新 applied
        db_run = session.get(StrategyRun, run.id)
        if db_run:
            db_run.applied = True
        session.commit()
    # 回写到调用方持有的 run 对象
    run.applied = True


def run_quant_strategy(
    strategy_class: type[BaseStrategy],
    strategy_file: str | None,
    params: dict,
    apply: bool = False,
    settings: Settings | None = None,
) -> QuantRunResult:
    """运行量化策略，落库，可选写入 TargetAllocation。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 合并参数：类默认 → CLI 覆盖
    strategy_instance = strategy_class()
    merged_params = {**strategy_instance.params, **params}

    ctx = _build_context(strategy_class, merged_params, app_settings)

    weights = strategy_instance.compute_weights(ctx)

    # 落库
    run = StrategyRun(
        strategy_name=strategy_class.__name__,
        strategy_file=strategy_file,
        params=json.dumps(merged_params),
        weights=json.dumps(weights),
        applied=False,
    )
    with get_session(app_settings) as session:
        session.add(run)
        session.commit()
        session.refresh(run)

    if apply:
        _apply_weights(run, weights, app_settings)

    return QuantRunResult(
        run_id=run.id,
        strategy_name=run.strategy_name,
        params=merged_params,
        weights=weights,
        applied=run.applied,
        run_at=run.run_at.isoformat(),
    )


def list_strategy_runs(
    limit: int = 10,
    run_id: int | None = None,
    settings: Settings | None = None,
) -> list[StrategyRunView]:
    """查询策略运行历史。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        if run_id is not None:
            row = session.get(StrategyRun, run_id)
            rows = [row] if row else []
        else:
            rows = session.exec(
                select(StrategyRun)
                .order_by(StrategyRun.run_at.desc())
                .limit(limit)
            ).all()

    return [
        StrategyRunView(
            id=r.id,
            strategy_name=r.strategy_name,
            strategy_file=r.strategy_file,
            params=json.loads(r.params),
            weights=json.loads(r.weights),
            applied=r.applied,
            run_at=r.run_at.isoformat(),
        )
        for r in rows
    ]
