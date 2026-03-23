"""状态摘要应用服务。"""

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.decision_logs import UserPreference
from hiveflow.domain.positions import Position
from hiveflow.domain.risk import RiskSignal
from hiveflow.domain.slots import StrategySlot
from hiveflow.domain.strategies import Strategy
from hiveflow.domain.suggestions import RebalanceSuggestion


@dataclass(frozen=True)
class SummaryStats:
    # 持仓条目数量。
    positions_count: int
    # 策略条目数量。
    strategies_count: int
    # 席位条目数量。
    slots_count: int
    # 启用席位数量。
    enabled_slots_count: int
    # 当前策略名称（可选）。
    current_strategy: str | None
    # 持仓总市值。
    total_market_value: float
    # 目标持仓条目数量。
    target_allocations_count: int
    # 风险信号总数量。
    risk_signals_count: int
    # 高风险信号数量。
    risk_high_count: int
    # 中风险信号数量。
    risk_medium_count: int
    # 低风险信号数量。
    risk_low_count: int
    # 调仓建议数量。
    rebalance_suggestions_count: int
    # 决策日志数量。
    decision_logs_count: int

    def to_dict(self) -> dict[str, int | float | str | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "positions_count": self.positions_count,
            "strategies_count": self.strategies_count,
            "slots_count": self.slots_count,
            "enabled_slots_count": self.enabled_slots_count,
            "current_strategy": self.current_strategy,
            "total_market_value": round(self.total_market_value, 2),
            "target_allocations_count": self.target_allocations_count,
            "risk_signals_count": self.risk_signals_count,
            "risk_high_count": self.risk_high_count,
            "risk_medium_count": self.risk_medium_count,
            "risk_low_count": self.risk_low_count,
            "rebalance_suggestions_count": self.rebalance_suggestions_count,
            "decision_logs_count": self.decision_logs_count,
        }


def get_summary_stats() -> SummaryStats:
    """读取数据库并生成状态摘要。"""
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()
        strategies = session.exec(select(Strategy)).all()
        slots = session.exec(select(StrategySlot)).all()
        target_allocations = session.exec(select(TargetAllocation)).all()
        risk_signals = session.exec(select(RiskSignal)).all()
        rebalance_suggestions = session.exec(select(RebalanceSuggestion)).all()
        decision_logs = session.exec(select(DecisionLog)).all()
        current_strategy_pref = session.exec(
            select(UserPreference).where(UserPreference.key == "current_strategy")
        ).first()

    total_market_value = sum(position.market_value for position in positions)
    risk_high_count = sum(
        1 for signal in risk_signals if signal.waterline.strip().lower() in {"high", "extreme"}
    )
    risk_medium_count = sum(
        1 for signal in risk_signals if signal.waterline.strip().lower() in {"medium", "mid"}
    )
    risk_low_count = max(len(risk_signals) - risk_high_count - risk_medium_count, 0)

    return SummaryStats(
        positions_count=len(positions),
        strategies_count=len(strategies),
        slots_count=len(slots),
        enabled_slots_count=sum(1 for slot in slots if slot.enabled),
        current_strategy=(current_strategy_pref.value if current_strategy_pref else None),
        total_market_value=total_market_value,
        target_allocations_count=len(target_allocations),
        risk_signals_count=len(risk_signals),
        risk_high_count=risk_high_count,
        risk_medium_count=risk_medium_count,
        risk_low_count=risk_low_count,
        rebalance_suggestions_count=len(rebalance_suggestions),
        decision_logs_count=len(decision_logs),
    )


def get_market_summary(settings=None) -> dict:
    """返回各市场持仓汇总（不做跨市场货币合算）。"""
    from hiveflow.domain.market import CRYPTO, CN_A_SHARE

    create_all_tables(settings)
    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()

    crypto_positions = [p for p in positions if getattr(p, "market", CRYPTO) == CRYPTO]
    cn_positions = [p for p in positions if getattr(p, "market", CRYPTO) == CN_A_SHARE]

    return {
        "markets": {
            CRYPTO: {
                "position_count": len(crypto_positions),
                "total_market_value_usdt": round(sum(p.market_value for p in crypto_positions), 2),
                "currency": "USDT",
            },
            CN_A_SHARE: {
                "position_count": len(cn_positions),
                "total_market_value_cny": round(sum(p.market_value for p in cn_positions), 2),
                "currency": "CNY",
            },
        },
        "note": "跨市场货币未合算，各市场独立展示",
    }
