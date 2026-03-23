from datetime import datetime, timedelta, timezone

from hiveflow.application.policy.rebalance_policy import RebalancePolicyInput
from hiveflow.application.policy.rebalance_policy import evaluate_rebalance_policy


def test_rebalance_policy_blocks_when_drift_too_small() -> None:
    result = evaluate_rebalance_policy(
        RebalancePolicyInput(
            drift_max_abs=0.01,
            risk_level="medium",
            now=datetime(2026, 3, 23, tzinfo=timezone.utc),
            min_drift_threshold=0.03,
        )
    )
    assert result.rebalance_allowed is False
    assert "drift_too_small" in result.reason_codes


def test_rebalance_policy_disables_buy_under_high_risk() -> None:
    result = evaluate_rebalance_policy(
        RebalancePolicyInput(
            drift_max_abs=0.08,
            risk_level="high",
            now=datetime(2026, 3, 23, tzinfo=timezone.utc),
        )
    )
    assert result.rebalance_allowed is True
    assert result.buy_allowed is False
    assert result.sell_allowed is True
    assert "risk_gate_buy_disabled" in result.reason_codes


def test_rebalance_policy_blocks_during_cooldown() -> None:
    now = datetime(2026, 3, 23, tzinfo=timezone.utc)
    result = evaluate_rebalance_policy(
        RebalancePolicyInput(
            drift_max_abs=0.08,
            risk_level="low",
            now=now,
            last_rebalance_at=now - timedelta(hours=1),
            cooldown_hours=24,
        )
    )
    assert result.rebalance_allowed is False
    assert result.cooldown_active is True
    assert "cooldown_active" in result.reason_codes

