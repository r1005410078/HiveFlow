from dataclasses import dataclass


@dataclass(frozen=True)
class UniverseRuleConfig:
    min_listed_days: int = 60
