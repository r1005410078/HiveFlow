from datetime import datetime, timedelta, timezone

from hiveflow.application.policy.strategy_switch_policy import StrategySwitchPolicyInput
from hiveflow.application.policy.strategy_switch_policy import evaluate_strategy_switch_policy


def test_switch_policy_requires_advantage_threshold() -> None:
    result = evaluate_strategy_switch_policy(
        StrategySwitchPolicyInput(
            current_strategy="MomentumStrategy",
            candidate_strategy="MeanReversionStrategy",
            current_score=0.55,
            candidate_score=0.62,
            min_advantage_score=0.10,
            now=datetime(2026, 3, 23, tzinfo=timezone.utc),
        )
    )
    assert result.switch_threshold_passed is False
    assert result.switch_allowed is False
    assert "advantage_not_enough" in result.reason_codes


def test_switch_policy_blocks_during_cooldown_even_if_threshold_passed() -> None:
    now = datetime(2026, 3, 23, tzinfo=timezone.utc)
    result = evaluate_strategy_switch_policy(
        StrategySwitchPolicyInput(
            current_strategy="MomentumStrategy",
            candidate_strategy="MeanReversionStrategy",
            current_score=0.50,
            candidate_score=0.80,
            min_advantage_score=0.10,
            now=now,
            last_switch_at=now - timedelta(hours=1),
            cooldown_hours=24,
        )
    )
    assert result.switch_threshold_passed is True
    assert result.cooldown_active is True
    assert result.switch_allowed is False
    assert "switch_cooldown_active" in result.reason_codes

