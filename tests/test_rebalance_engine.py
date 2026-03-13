from hiveflow.services.rebalance_engine import compare_actual_to_target
from hiveflow.services.rebalance_engine import generate_rebalance_suggestions
from hiveflow.services.risk_engine import classify_priority_from_risk


def test_compare_actual_to_target_calculates_deltas() -> None:
    # 验证每个标的的偏差值按“实际权重 - 目标权重”计算。
    result = compare_actual_to_target(
        actual={"BTC": 0.6, "ETH": 0.2, "USDT": 0.2},
        target={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert result["BTC"] == 0.1
    assert result["ETH"] == -0.1


def test_generate_rebalance_suggestions_includes_action_and_priority() -> None:
    # 验证建议结果包含动作方向与处理优先级。
    suggestions = generate_rebalance_suggestions(
        actual={"BTC": 0.6, "ETH": 0.2, "USDT": 0.2},
        target={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert suggestions[0].action in {"buy", "sell", "hold"}
    assert suggestions[0].priority in {"high", "medium", "low"}


def test_high_risk_maps_to_high_priority() -> None:
    # 验证高风险水位会映射为高优先级处理。
    assert classify_priority_from_risk("high") == "high"
