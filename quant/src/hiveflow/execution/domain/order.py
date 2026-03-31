from dataclasses import dataclass


@dataclass(frozen=True)
class Order:
    symbol: str
    target_notional: float
