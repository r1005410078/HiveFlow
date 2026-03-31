from hiveflow.execution.application.plan_use_case import build_plan


def test_build_plan_orders():
    """验证 L6 能生成与输入权重对应的执行订单。"""
    p = build_plan([{"symbol": "000001.SZ", "target_weight": 0.2}], cash=100000)
    assert len(p["orders"]) == 1
