from typing import List

from pydantic import BaseModel


class DailyRunRequest(BaseModel):
    as_of: str


class FactorRow(BaseModel):
    as_of: str
    symbol: str
    factor_name: str
    factor_version: str
    raw_value: float


class FactorSnapshot(BaseModel):
    factor_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[FactorRow]


class ExecutionPlan(BaseModel):
    orders: list[dict]


class FactorBreakdown(BaseModel):
    factor_name: str
    raw_value: float
    normalized_value: float
    percentile: float
    clipped: bool
    anomaly_flags: List[str]
    weight: float
    contribution: float


class L2ScoreBreakdownItem(BaseModel):
    symbol: str
    final_score: float
    factors: List[FactorBreakdown]


class L2TopCandidate(BaseModel):
    symbol: str
    score: float
    rank: int


class L2Decision(BaseModel):
    schema_version: str
    generated_at: str
    producer_version: str
    score_version: str
    universe_size: int
    top_candidates: List[L2TopCandidate]
    score_breakdown: List[L2ScoreBreakdownItem]


class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan
    l2_decision: L2Decision


class DailyRunResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: DailyRunData
    warnings: list[dict]
    errors: list[dict]
