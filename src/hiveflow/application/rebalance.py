"""调仓预览应用服务。"""

from dataclasses import dataclass

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.positions import Position
from hiveflow.domain.strategies import Strategy
from hiveflow.domain.suggestions import RebalanceSuggestion
from hiveflow.services.rebalance_engine import generate_rebalance_suggestions


@dataclass(frozen=True)
class RebalanceSuggestionView:
    # 标的代码。
    symbol: str
    # 偏差值（实际权重 - 目标权重）。
    delta: float
    # 建议动作：buy/sell/hold。
    action: str
    # 优先级：high/medium/low。
    priority: str
    # 建议原因。
    reason: str

    def to_dict(self) -> dict[str, str | float]:
        return {
            "symbol": self.symbol,
            "delta": round(self.delta, 6),
            "action": self.action,
            "priority": self.priority,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class RebalancePreviewResult:
    # 本次预览使用的策略名；None 表示使用所有目标持仓。
    strategy: str | None
    # 策略类型。
    strategy_type: str | None
    # 策略维度。
    dimension: str | None
    # 结构化建议列表。
    suggestions: list[RebalanceSuggestionView]
    # 是否已落库保存。
    saved: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "strategy_type": self.strategy_type,
            "dimension": self.dimension,
            "suggestions_count": len(self.suggestions),
            "saved": self.saved,
            "suggestions": [item.to_dict() for item in self.suggestions],
        }


def _collect_actual_weights() -> dict[str, float]:
    """读取实际持仓权重映射。

    Returns:
        dict[str, float]: 键为标的代码，值为当前实际权重。
    """
    create_all_tables()
    with get_session() as session:
        positions = session.exec(select(Position)).all()
    return {position.symbol: position.weight for position in positions}


def _collect_target_weights(strategy: str | None) -> dict[str, float]:
    """读取目标持仓权重映射。

    Args:
        strategy: 策略名称。传 None 时返回全部策略目标持仓的合并结果。

    Returns:
        dict[str, float]: 键为标的代码，值为目标权重。
    """
    create_all_tables()
    with get_session() as session:
        targets = session.exec(select(TargetAllocation)).all()

    if strategy:
        filtered = [item for item in targets if item.strategy_name == strategy]
    else:
        filtered = targets

    result: dict[str, float] = {}
    for target in filtered:
        result[target.symbol] = result.get(target.symbol, 0.0) + target.target_weight
    return result


def _save_suggestions(items: list[RebalanceSuggestionView]) -> None:
    """将调仓建议持久化到数据库。

    Args:
        items: 待保存的建议列表。该方法会先清空旧建议再写入新建议。
    """
    create_all_tables()
    with get_session() as session:
        session.exec(delete(RebalanceSuggestion))
        session.add_all(
            [
                RebalanceSuggestion(
                    symbol=item.symbol,
                    delta=item.delta,
                    action=item.action,
                    priority=item.priority,
                    reason=item.reason,
                )
                for item in items
            ]
        )
        session.commit()


def preview_rebalance(
    strategy: str | None = None,
    save: bool = False,
) -> RebalancePreviewResult:
    """预览调仓建议，可选持久化到数据库。

    Args:
        strategy: 指定策略名；为 None 时使用全部目标持仓。
        save: 是否将本次建议覆盖写入数据库。

    Returns:
        RebalancePreviewResult: 包含预览结果、策略名和保存状态。
    """
    actual = _collect_actual_weights()
    target = _collect_target_weights(strategy=strategy)
    suggestions = generate_rebalance_suggestions(actual=actual, target=target)
    suggestion_views = [
        RebalanceSuggestionView(
            symbol=item.symbol,
            delta=item.delta,
            action=item.action,
            priority=item.priority,
            reason=item.reason,
        )
        for item in suggestions
    ]

    if save:
        _save_suggestions(suggestion_views)

    strategy_type: str | None = None
    dimension: str | None = None
    if strategy:
        with get_session() as session:
            strategy_row = session.exec(select(Strategy).where(Strategy.name == strategy)).first()
        if strategy_row:
            strategy_type = strategy_row.category
            dimension = strategy_row.dimension

    return RebalancePreviewResult(
        strategy=strategy,
        strategy_type=strategy_type,
        dimension=dimension,
        saved=save,
        suggestions=suggestion_views,
    )
