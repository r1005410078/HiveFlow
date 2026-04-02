from typing import Literal

from pydantic import BaseModel, Field


class DailyRunRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 `YYYY-MM-DD`，只使用该日期前的数据（PIT 语义）")


class PipelineCompareRequest(BaseModel):
    start_date: str = Field(description="对比起始日期，格式 `YYYY-MM-DD`")
    end_date: str = Field(description="对比结束日期，格式 `YYYY-MM-DD`")
    top_n: int = Field(default=5, ge=1, le=50, description="每个版本保留的候选数")


class FactorOptimizationEvaluateRequest(BaseModel):
    start_date: str = Field(description="分析起始日期，格式 `YYYY-MM-DD`")
    end_date: str = Field(description="分析结束日期，格式 `YYYY-MM-DD`")
    factor_names: list[str] = Field(description="待评估因子列表")
    constraints: dict[str, float] = Field(default_factory=dict, description="权重约束，如 `max_weight:max_drawdown_60: 0.3`")


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


class L2FactorAvailability(BaseModel):
    factor_name: str
    present_count: int
    missing_count: int
    availability_rate: float


class L2Decision(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: str
    producer_version: Literal["quant-l2"] = "quant-l2"
    score_version: Literal["l2-score-v1", "l2-score-v1.1"] = "l2-score-v1.1"
    universe_size: int
    top_candidates: list[L2TopCandidate]
    score_breakdown: list[L2ScoreBreakdownItem]
    factor_availability: list[L2FactorAvailability]


class PipelineCompareVersion(BaseModel):
    score_version: Literal["l2-score-v1", "l2-score-v1.1"]
    top_candidates: list[L2TopCandidate]
    warning_count: int
    min_availability: float
    error: str | None = None


class PipelineCompareDailyItem(BaseModel):
    as_of: str
    v1: PipelineCompareVersion
    v1_1: PipelineCompareVersion


class PipelineCompareSummary(BaseModel):
    days: int
    avg_warning_count_v1: float
    avg_warning_count_v1_1: float
    avg_min_availability_v1: float
    avg_min_availability_v1_1: float
    top1_symbol_change_days: int


class PipelineCompareData(BaseModel):
    start_date: str
    end_date: str
    top_n: int
    score_versions: list[str]
    daily_items: list[PipelineCompareDailyItem]
    summary: PipelineCompareSummary


class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan
    l2_decision: L2Decision


class PipelineCompareResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: PipelineCompareData
    warnings: list[dict]
    errors: list[dict]


class FactorOptimizationEvaluateResponse(BaseModel):
    schema_version: str
    command: str
    status: str
    advice_only: bool
    decision_weight: int
    data: dict
    audit: dict
    warnings: list[dict]
    errors: list[dict]


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
