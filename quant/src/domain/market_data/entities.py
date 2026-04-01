from dataclasses import dataclass


@dataclass(frozen=True)
class Bar:
    symbol: str
    timeframe: str
    bar_time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    amount: float
    adj_factor: float = 1.0

