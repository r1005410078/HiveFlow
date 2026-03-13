from hiveflow.domain.suggestions import RebalanceSuggestion
from hiveflow.domain.value_objects import PriorityLevel
from hiveflow.domain.value_objects import RebalanceAction


def compare_actual_to_target(
    actual: dict[str, float], target: dict[str, float]
) -> dict[str, float]:
    """计算每个标的的权重偏差（实际 - 目标）。"""
    symbols = set(actual) | set(target)
    return {
        symbol: round(actual.get(symbol, 0.0) - target.get(symbol, 0.0), 10)
        for symbol in symbols
    }


def generate_rebalance_suggestions(
    actual: dict[str, float], target: dict[str, float]
) -> list[RebalanceSuggestion]:
    """基于实际与目标偏差生成调仓建议。

    返回结果包含动作、优先级和原因说明。
    """
    deltas = compare_actual_to_target(actual=actual, target=target)
    suggestions: list[RebalanceSuggestion] = []

    for symbol in sorted(deltas):
        delta = deltas[symbol]
        abs_delta = abs(delta)
        if delta > 0:
            action = RebalanceAction.SELL
        elif delta < 0:
            action = RebalanceAction.BUY
        else:
            action = RebalanceAction.HOLD

        if abs_delta >= 0.1:
            priority = PriorityLevel.HIGH
        elif abs_delta >= 0.05:
            priority = PriorityLevel.MEDIUM
        else:
            priority = PriorityLevel.LOW

        suggestions.append(
            RebalanceSuggestion(
                symbol=symbol,
                delta=delta,
                action=action,
                priority=priority,
                reason=f"Current weight delta is {delta:+.2%}.",
            )
        )

    return suggestions
