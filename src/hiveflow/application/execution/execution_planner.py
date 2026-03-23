"""Build executable rebalance plans from candidate actions."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RebalanceAction:
    symbol: str
    action: str
    priority: str
    allowed: bool
    reason_codes: list[str]
    estimated_usdt: float


@dataclass(frozen=True)
class ExecutionPlan:
    plan_state: str
    orders: list[RebalanceAction]
    skipped: list[RebalanceAction]


def build_execution_plan(actions: list[RebalanceAction]) -> ExecutionPlan:
    orders = [action for action in actions if action.allowed]
    skipped = [action for action in actions if not action.allowed]
    plan_state = "ready_for_confirmation" if orders else "review_only"
    return ExecutionPlan(plan_state=plan_state, orders=orders, skipped=skipped)

