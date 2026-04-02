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


class DailyRunData(BaseModel):
    as_of: str
    data_manifest_id: str
    factor_snapshot: FactorSnapshot
    execution_plan: ExecutionPlan


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
