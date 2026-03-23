"""Deterministic rebalance gating policy."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class RebalancePolicyInput:
    drift_max_abs: float
    risk_level: str
    now: datetime
    min_drift_threshold: float = 0.03
    last_rebalance_at: datetime | None = None
    cooldown_hours: int = 24


@dataclass(frozen=True)
class RebalancePolicyResult:
    rebalance_allowed: bool
    buy_allowed: bool
    sell_allowed: bool
    cooldown_active: bool
    reason_codes: list[str]


def evaluate_rebalance_policy(policy_input: RebalancePolicyInput) -> RebalancePolicyResult:
    reason_codes: list[str] = []

    cooldown_active = False
    if (
        policy_input.last_rebalance_at is not None
        and policy_input.cooldown_hours > 0
        and (policy_input.now - policy_input.last_rebalance_at)
        < timedelta(hours=policy_input.cooldown_hours)
    ):
        cooldown_active = True
        reason_codes.append("cooldown_active")

    drift_threshold_passed = policy_input.drift_max_abs >= policy_input.min_drift_threshold
    if not drift_threshold_passed:
        reason_codes.append("drift_too_small")

    buy_allowed = True
    sell_allowed = True
    if policy_input.risk_level.lower() == "high":
        buy_allowed = False
        reason_codes.append("risk_gate_buy_disabled")

    rebalance_allowed = drift_threshold_passed and not cooldown_active
    return RebalancePolicyResult(
        rebalance_allowed=rebalance_allowed,
        buy_allowed=buy_allowed,
        sell_allowed=sell_allowed,
        cooldown_active=cooldown_active,
        reason_codes=reason_codes,
    )

