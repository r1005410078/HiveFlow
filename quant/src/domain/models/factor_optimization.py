from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FactorHealthItem:
    factor_name: str
    ic: float
    sharpe: float
    max_drawdown: float


@dataclass
class WeightScheme:
    name: str
    weights: dict[str, float]
    expected_sharpe: float
    expected_drawdown: float
    score: float
