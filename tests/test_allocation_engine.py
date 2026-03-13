from hiveflow.services.allocation_engine import generate_target_allocations


def test_generate_target_allocations_returns_targets_for_selected_strategy() -> None:
    # 验证根据输入权重能生成对应标的的目标持仓记录。
    targets = generate_target_allocations(
        strategy_name="测试趋势策略",
        allocations={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert len(targets) == 3
    assert targets[0].strategy_name == "测试趋势策略"
