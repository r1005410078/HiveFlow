from dataclasses import dataclass


@dataclass(frozen=True)
class TargetWeightRow:
    symbol: str
    weight: float
    prev_weight: float
    delta: float


@dataclass(frozen=True)
class OptimizationReport:
    objective_value: float
    risk_contribution: float
    turnover_cost: float
    solver: str
    solve_time_ms: int


@dataclass(frozen=True)
class PortfolioOptimizationResult:
    as_of: str
    optimize_version: str
    optimization_status: str  # optimal|optimal_inaccurate|fallback_equal_weight|fallback_prev_weight
    fallback_reason: str | None
    target_weights: tuple[TargetWeightRow, ...]
    optimization_report: OptimizationReport
