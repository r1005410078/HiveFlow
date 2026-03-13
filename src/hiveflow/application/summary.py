"""状态摘要应用服务。"""

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.suggestions import RebalanceSuggestion


@dataclass(frozen=True)
class SummaryStats:
    positions_count: int
    total_market_value: float
    target_allocations_count: int
    risk_signals_count: int
    rebalance_suggestions_count: int

    def to_dict(self) -> dict[str, int | float]:
        return {
            "positions_count": self.positions_count,
            "total_market_value": round(self.total_market_value, 2),
            "target_allocations_count": self.target_allocations_count,
            "risk_signals_count": self.risk_signals_count,
            "rebalance_suggestions_count": self.rebalance_suggestions_count,
        }


def get_summary_stats() -> SummaryStats:
    """读取数据库并生成状态摘要。"""
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()
        target_allocations = session.exec(select(TargetAllocation)).all()
        risk_signals = session.exec(select(RiskSignal)).all()
        rebalance_suggestions = session.exec(select(RebalanceSuggestion)).all()

    total_market_value = sum(position.market_value for position in positions)
    return SummaryStats(
        positions_count=len(positions),
        total_market_value=total_market_value,
        target_allocations_count=len(target_allocations),
        risk_signals_count=len(risk_signals),
        rebalance_suggestions_count=len(rebalance_suggestions),
    )

