from dataclasses import dataclass


@dataclass(frozen=True)
class FactorValue:
    as_of: str
    symbol: str
    name: str
    value: float
    factor_version: str
    direction: int
    unit: str
    missing_strategy: str
    source: str  # "real" | "deterministic_fallback" | "benchmark_proxy_fallback"
