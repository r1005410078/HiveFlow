from typing import List
from dataclasses import dataclass


@dataclass
class FactorDetail:
    factor_name: str
    raw_value: float
    normalized_value: float
    percentile: float
    clipped: bool
    anomaly_flags: List[str]
    weight: float
    contribution: float


@dataclass
class ScoreBreakdownItem:
    symbol: str
    final_score: float
    factors: List[FactorDetail]


@dataclass
class TopCandidate:
    symbol: str
    score: float
    rank: int
