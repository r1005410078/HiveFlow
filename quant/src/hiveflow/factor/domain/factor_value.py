from dataclasses import dataclass


@dataclass(frozen=True)
class FactorValue:
    name: str
    value: float
    as_of: str
