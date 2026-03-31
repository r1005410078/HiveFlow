from dataclasses import dataclass


@dataclass(frozen=True)
class SignalValue:
    symbol: str
    value: float
    as_of: str
