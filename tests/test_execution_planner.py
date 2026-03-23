from hiveflow.application.execution.execution_planner import RebalanceAction
from hiveflow.application.execution.execution_planner import build_execution_plan


def test_execution_plan_ready_for_confirmation_when_orders_exist() -> None:
    plan = build_execution_plan(
        [
            RebalanceAction(
                symbol="BTC",
                action="sell",
                priority="high",
                allowed=True,
                reason_codes=[],
                estimated_usdt=800.0,
            ),
            RebalanceAction(
                symbol="ETH",
                action="buy",
                priority="medium",
                allowed=False,
                reason_codes=["risk_gate_buy_disabled"],
                estimated_usdt=500.0,
            ),
        ]
    )
    assert plan.plan_state == "ready_for_confirmation"
    assert len(plan.orders) == 1
    assert len(plan.skipped) == 1


def test_execution_plan_review_only_when_all_actions_blocked() -> None:
    plan = build_execution_plan(
        [
            RebalanceAction(
                symbol="ETH",
                action="buy",
                priority="high",
                allowed=False,
                reason_codes=["risk_gate_buy_disabled"],
                estimated_usdt=600.0,
            )
        ]
    )
    assert plan.plan_state == "review_only"
    assert len(plan.orders) == 0
    assert len(plan.skipped) == 1

