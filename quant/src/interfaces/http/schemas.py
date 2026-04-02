from typing import Literal

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
    anomaly_flags: list[str]
    weight: float
    contribution: float


class L2ScoreBreakdownItem(BaseModel):
    symbol: str
    final_score: float
    factors: list[FactorBreakdown]


class L2TopCandidate(BaseModel):
    symbol: str
    score: float
    rank: int


class L2Decision(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: str
    producer_version: Literal["quant-l2"] = "quant-l2"
    score_version: Literal["l2-score-v1"] = "l2-score-v1"
    universe_size: int
    top_candidates: list[L2TopCandidate]
    score_breakdown: list[L2ScoreBreakdownItem]


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
