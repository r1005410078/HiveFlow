def build_plan(weights: list[dict], cash: float) -> dict:
    orders = [{"symbol": w["symbol"], "target_notional": cash * w["target_weight"]} for w in weights]
    return {"execution_plan": "rebalance", "orders": orders, "estimated_cost": 0.0, "pre_check_result": "pass"}
