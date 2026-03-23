"""Deterministic policy for strategy switching."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class StrategySwitchPolicyInput:
    current_strategy: str
    candidate_strategy: str
    current_score: float
    candidate_score: float
    min_advantage_score: float
    now: datetime
    last_switch_at: datetime | None = None
    cooldown_hours: int = 24


@dataclass(frozen=True)
class StrategySwitchPolicyResult:
    switch_allowed: bool
    switch_threshold_passed: bool
    cooldown_active: bool
    advantage_score: float
    reason_codes: list[str]


def evaluate_strategy_switch_policy(
    policy_input: StrategySwitchPolicyInput,
) -> StrategySwitchPolicyResult:
    reason_codes: list[str] = []

    advantage_score = policy_input.candidate_score - policy_input.current_score
    switch_threshold_passed = advantage_score >= policy_input.min_advantage_score
    if not switch_threshold_passed:
        reason_codes.append("advantage_not_enough")

    cooldown_active = False
    if (
        policy_input.last_switch_at is not None
        and policy_input.cooldown_hours > 0
        and (policy_input.now - policy_input.last_switch_at)
        < timedelta(hours=policy_input.cooldown_hours)
    ):
        cooldown_active = True
        reason_codes.append("switch_cooldown_active")

    switch_allowed = switch_threshold_passed and not cooldown_active
    return StrategySwitchPolicyResult(
        switch_allowed=switch_allowed,
        switch_threshold_passed=switch_threshold_passed,
        cooldown_active=cooldown_active,
        advantage_score=advantage_score,
        reason_codes=reason_codes,
    )

