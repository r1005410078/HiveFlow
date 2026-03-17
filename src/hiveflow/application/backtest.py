"""回测应用服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.services.backtest_engine import load_close_prices
from hiveflow.services.backtest_engine import load_close_prices_from_db
from hiveflow.services.backtest_engine import run_weighted_backtest


@dataclass(frozen=True)
class BacktestResultView:
    """回测结果视图。"""

    id: int | None
    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None
    created_at: str

    def to_dict(self) -> dict[str, str | float | int | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "prices_file": self.prices_file,
            "periods": self.periods,
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "sharpe": round(self.sharpe, 6),
            "weights_snapshot": self.weights_snapshot,
            "created_at": self.created_at,
        }


def _to_view(row: BacktestResult) -> BacktestResultView:
    return BacktestResultView(
        id=row.id,
        strategy_name=row.strategy_name,
        prices_file=row.prices_file,
        periods=row.periods,
        total_return=row.total_return,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        weights_snapshot=row.weights_snapshot,
        created_at=row.created_at.isoformat(),
    )


def _load_target_weights(strategy_name: str, settings=None) -> dict[str, float]:
    """加载策略目标权重。"""
    create_all_tables(settings)
    with get_session(settings) as session:
        rows = session.exec(
            select(TargetAllocation).where(TargetAllocation.strategy_name == strategy_name)
        ).all()
    if not rows:
        raise ValueError("策略没有目标持仓，请先执行 targets generate 或导入 targets。")
    return {item.symbol: item.target_weight for item in rows}


def run_backtest_for_strategy(
    strategy_name: str,
    prices_file: Path | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    settings=None,
) -> BacktestResultView:
    """执行单策略回测并持久化结果。"""
    weights = _load_target_weights(strategy_name=strategy_name, settings=settings)

    if prices_file is not None:
        prices = load_close_prices(file=prices_file)
        source = str(prices_file)
    else:
        prices = load_close_prices_from_db(symbols=list(weights.keys()), settings=settings)
        source = "DB:MarketBar"

    metrics = run_weighted_backtest(
        prices=prices,
        weights=weights,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    create_all_tables(settings)
    with get_session(settings) as session:
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file=source,
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(weights),
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return _to_view(row)


def list_backtest_results(strategy_name: str | None = None, settings=None) -> list[BacktestResultView]:
    """查询历史回测结果。"""
    create_all_tables(settings)
    with get_session(settings) as session:
        rows = session.exec(select(BacktestResult)).all()
    if strategy_name:
        rows = [item for item in rows if item.strategy_name == strategy_name]
    ordered = sorted(rows, key=lambda item: item.created_at, reverse=True)
    return [_to_view(item) for item in ordered]
