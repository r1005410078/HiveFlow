from datetime import datetime, timezone

from hiveflow.application.evaluation.strategy_evaluation import build_strategy_evaluation


def test_strategy_evaluation_marks_healthy_when_scores_are_good() -> None:
    evaluation = build_strategy_evaluation(
        strategy="MomentumStrategy",
        current_market_fit="high",
        backtest_quality_score=0.82,
        stability_score=0.76,
        as_of=datetime(2026, 3, 23, tzinfo=timezone.utc),
    )
    assert evaluation.strategy_health == "healthy"
    assert evaluation.degradation_flag is False
    assert evaluation.current_market_fit == "high"


def test_strategy_evaluation_marks_paused_when_scores_are_low() -> None:
    evaluation = build_strategy_evaluation(
        strategy="MomentumStrategy",
        current_market_fit="low",
        backtest_quality_score=0.35,
        stability_score=0.31,
        as_of=datetime(2026, 3, 23, tzinfo=timezone.utc),
    )
    assert evaluation.strategy_health == "paused"
    assert evaluation.degradation_flag is True

