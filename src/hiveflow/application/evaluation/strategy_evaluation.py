"""Strategy health evaluation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StrategyEvaluation:
    strategy: str
    current_market_fit: str
    backtest_quality_score: float
    stability_score: float
    composite_score: float
    strategy_health: str
    degradation_flag: bool
    as_of: datetime


def build_strategy_evaluation(
    strategy: str,
    current_market_fit: str,
    backtest_quality_score: float,
    stability_score: float,
    as_of: datetime,
) -> StrategyEvaluation:
    composite_score = (backtest_quality_score + stability_score) / 2.0

    if current_market_fit == "low" or composite_score < 0.50:
        strategy_health = "paused"
        degradation_flag = True
    elif current_market_fit == "medium" or composite_score < 0.70:
        strategy_health = "watch"
        degradation_flag = False
    else:
        strategy_health = "healthy"
        degradation_flag = False

    return StrategyEvaluation(
        strategy=strategy,
        current_market_fit=current_market_fit,
        backtest_quality_score=backtest_quality_score,
        stability_score=stability_score,
        composite_score=composite_score,
        strategy_health=strategy_health,
        degradation_flag=degradation_flag,
        as_of=as_of,
    )

