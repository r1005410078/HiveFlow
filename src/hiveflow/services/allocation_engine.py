from hiveflow.domain.allocations import TargetAllocation


def generate_target_allocations(
    strategy_name: str, allocations: dict[str, float]
) -> list[TargetAllocation]:
    """根据策略名和目标权重字典，生成目标持仓记录列表。"""
    return [
        TargetAllocation(
            strategy_name=strategy_name,
            symbol=symbol,
            target_weight=weight,
        )
        for symbol, weight in allocations.items()
    ]
