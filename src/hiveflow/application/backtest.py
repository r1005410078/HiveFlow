"""回测应用服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.services.backtest_engine import load_close_prices
from hiveflow.services.backtest_engine import load_close_prices_from_db
from hiveflow.services.backtest_engine import run_weighted_backtest

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from hiveflow.services.strategies.base import BaseStrategy


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
    backtest_type: str
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
            "backtest_type": self.backtest_type,
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
        backtest_type=row.backtest_type,
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
            backtest_type="static",
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


def run_quant_backtest(
    strategy: "BaseStrategy",
    rebalance_days: int = 7,
    symbols: list[str] | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    settings=None,
) -> BacktestResultView:
    """执行量化策略动态回测并持久化结果。

    strategy: 已实例化的 BaseStrategy 子类
    rebalance_days: 再平衡周期（天）
    symbols: 指定资产池；None 时自动从 MarketBar 读取所有 symbol
    """
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.services.backtest_engine import run_dynamic_backtest

    create_all_tables(settings)

    # 解析资产池
    if symbols is None:
        with get_session(settings) as session:
            rows = session.exec(select(MarketBar.symbol).distinct()).all()
        symbols = list(rows)
    if not symbols:
        raise ValueError("MarketBar 中没有数据，请先运行 hiveflow market-data import。")

    prices = load_close_prices_from_db(symbols=symbols, settings=settings)
    if not prices:
        raise ValueError("指定 symbol 在 MarketBar 中无数据，请先运行 hiveflow market-data import。")

    metrics, final_weights = run_dynamic_backtest(
        prices=prices,
        strategy=strategy,
        rebalance_days=rebalance_days,
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    strategy_name = type(strategy).__name__

    with get_session(settings) as session:
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file="DB:MarketBar",
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=json.dumps(final_weights),
            backtest_type="dynamic",
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return _to_view(row)


def set_targets_from_backtest(backtest_id: int, settings=None) -> dict[str, float]:
    """从回测结果的 weights_snapshot 设置目标配比。返回写入的配比字典。"""
    create_all_tables(settings)
    with get_session(settings) as session:
        row = session.get(BacktestResult, backtest_id)
        if row is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        if not row.weights_snapshot:
            raise ValueError(f"回测记录 #{backtest_id} 无 weights_snapshot，无法设置目标配比。")
        weights = json.loads(row.weights_snapshot)
        strategy_name = row.strategy_name

        session.exec(delete(TargetAllocation).where(
            TargetAllocation.strategy_name == strategy_name
        ))
        for symbol, weight in weights.items():
            session.add(TargetAllocation(
                strategy_name=strategy_name,
                symbol=symbol,
                target_weight=weight,
            ))
        session.commit()
    return weights
