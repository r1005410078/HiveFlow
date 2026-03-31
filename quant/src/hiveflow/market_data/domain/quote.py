from dataclasses import dataclass


@dataclass(frozen=True)
class Quote:
    symbol: str
    close: float
    volume: float
    adj_factor: float
    effective_date: str
