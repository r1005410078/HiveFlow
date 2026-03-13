"""回测应用服务。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.services.backtest_engine import load_close_prices
from hiveflow.services.backtest_engine import run_weighted_backtest


@dataclass(frozen=True)
class BacktestResultView:
    """回测结果视图。"""

    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    created_at: str

    def to_dict(self) -> dict[str, str | float | int]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "strategy_name": self.strategy_name,
            "prices_file": self.prices_file,
            "periods": self.periods,
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "sharpe": round(self.sharpe, 6),
            "created_at": self.created_at,
        }


def _load_target_weights(strategy_name: str) -> dict[str, float]:
    """加载策略目标权重。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(
            select(TargetAllocation).where(TargetAllocation.strategy_name == strategy_name)
        ).all()
    if not rows:
        raise ValueError("策略没有目标持仓，请先执行 targets generate 或导入 targets。")
    return {item.symbol: item.target_weight for item in rows}


def run_backtest_for_strategy(
    strategy_name: str,
    prices_file: Path,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> BacktestResultView:
    """执行单策略回测并持久化结果。"""
    weights = _load_target_weights(strategy_name=strategy_name)
    prices = load_close_prices(file=prices_file)
    metrics = run_weighted_backtest(
        prices=prices,
        weights=weights,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file=str(prices_file),
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return BacktestResultView(
        strategy_name=row.strategy_name,
        prices_file=row.prices_file,
        periods=row.periods,
        total_return=row.total_return,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        created_at=row.created_at.isoformat(),
    )


def list_backtest_results(strategy_name: str | None = None) -> list[BacktestResultView]:
    """查询历史回测结果。"""
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(BacktestResult)).all()
    if strategy_name:
        rows = [item for item in rows if item.strategy_name == strategy_name]
    ordered = sorted(rows, key=lambda item: item.created_at, reverse=True)
    return [
        BacktestResultView(
            strategy_name=item.strategy_name,
            prices_file=item.prices_file,
            periods=item.periods,
            total_return=item.total_return,
            max_drawdown=item.max_drawdown,
            sharpe=item.sharpe,
            created_at=item.created_at.isoformat(),
        )
        for item in ordered
    ]
