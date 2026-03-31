from dataclasses import dataclass


@dataclass(frozen=True)
class TargetWeight:
    symbol: str
    target_weight: float
