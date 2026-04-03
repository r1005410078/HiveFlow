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


@dataclass(frozen=True)
class DailyICEntry:
    date: str
    ic: float


@dataclass(frozen=True)
class FactorICResult:
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: tuple[DailyICEntry, ...]


@dataclass(frozen=True)
class FactorDriftResult:
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


@dataclass(frozen=True)
class RankTurnoverResult:
    mean_turnover: float
    max_turnover: float
    stable: bool
