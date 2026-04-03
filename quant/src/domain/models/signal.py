from dataclasses import dataclass


@dataclass(frozen=True)
class SignalRow:
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int


@dataclass(frozen=True)
class TransformStatsDetail:
    count: int
    mean: float
    std: float
    min_val: float
    max_val: float


@dataclass(frozen=True)
class TransformStats:
    factor_name: str
    pre_winsorize: TransformStatsDetail
    post_zscore: TransformStatsDetail


@dataclass(frozen=True)
class CompositeScore:
    symbol: str
    composite_score: float
    factor_count: int
