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
    correlation_threshold: float = Field(
        default=0.7,
        gt=0.0,
        le=1.0,
        description="相关性告警阈值，范围 `(0, 1]`，默认 `0.7`",
    )
    combination_size_min: int = Field(default=2, ge=2, le=4, description="组合最小因子数，默认 `2`")
    combination_size_max: int = Field(default=4, ge=2, le=4, description="组合最大因子数，默认 `4`")
    top_k_combinations: int = Field(default=5, ge=1, le=20, description="返回组合数量，默认 `5`")


class FactorRow(BaseModel):
    as_of: str
    symbol: str
    factor_name: str
    factor_version: str
    raw_value: float
    direction: int
    unit: str
    missing_strategy: str
    source: str


class FactorStabilityMetric(BaseModel):
    factor_name: str
    factor_version: str
    coverage_rate: float
    real_count: int
    fallback_count: int
    mean_value: float
    std_value: float
    drift_flag: bool | None = None
    drift_z_score: float | None = None


class FactorSnapshot(BaseModel):
    snapshot_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[FactorRow]
    stability_metrics: list[FactorStabilityMetric] = []


class ExecutionPlan(BaseModel):
    """L6 execution plan payload embedded in daily run ``data.execution_plan``."""

    orders: list[dict]
    as_of: str | None = None
    slippage_bp: float | None = None
    estimated_total_cost_bp: float | None = None


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


class SignalSnapshotRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
    universes: list[str] = Field(
        default_factory=list,
        description=(
            "与 default 合并的额外标的池名称（对应 quant/config/universes/{name}.txt）；"
            "未传或空列表时仅使用 default"
        ),
    )


class SignalRowSchema(BaseModel):
    symbol: str
    factor_name: str
    raw_value: float
    signal_value: float
    direction: int


class SignalCompositeScore(BaseModel):
    symbol: str
    composite_score: float
    factor_count: int


class SignalTransformStatsDetail(BaseModel):
    count: int
    mean: float
    std: float
    min: float
    max: float


class SignalTransformStats(BaseModel):
    factor_name: str
    pre_winsorize: SignalTransformStatsDetail
    post_zscore: SignalTransformStatsDetail


class SignalMatrix(BaseModel):
    schema_version: str
    generated_at: str
    producer_version: str
    signal_version: str
    factor_names: list[str]
    coverage_rate: float
    rows: list[SignalRowSchema]
    composite_scores: list[SignalCompositeScore]
    transform_stats: list[SignalTransformStats]


class MaCrossSymbolState(BaseModel):
    golden_cross: bool
    death_cross: bool
    sma5: float | None = None
    sma10: float | None = None
    available: bool


class MaCrossBlock(BaseModel):
    schema_version: str
    definition: str
    as_of: str
    by_symbol: dict[str, MaCrossSymbolState]


class TechnicalIndicators(BaseModel):
    ma5_ma10: MaCrossBlock | None = None


class SignalSnapshotData(BaseModel):
    """L3 矩阵 + 非 L3 技术字段（如 MA 交叉）；与 ``run_signal_snapshot`` 返回的 ``data`` 对齐。"""

    signal_matrix: SignalMatrix
    technical: TechnicalIndicators | None = None


class SignalSnapshotResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalSnapshotData
    warnings: list[dict]
    errors: list[dict]


class SignalEvaluateRequest(BaseModel):
    start_date: str = Field(description="评估起始日期，YYYY-MM-DD")
    end_date: str = Field(description="评估结束日期，YYYY-MM-DD")
    forward_days: int = Field(default=1, ge=1, le=10, description="前瞻天数")


class DailyIC(BaseModel):
    date: str
    ic: float


class FactorICReport(BaseModel):
    factor_name: str
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]


class CompositeICReport(BaseModel):
    mean_ic: float
    ic_std: float
    ic_ir: float
    hit_rate: float
    daily_ic: list[DailyIC]


class ICReport(BaseModel):
    per_factor: list[FactorICReport]
    composite: CompositeICReport


class FactorDrift(BaseModel):
    factor_name: str
    baseline_mean: float
    baseline_std: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


class CoverageDrift(BaseModel):
    baseline_mean: float
    recent_mean: float
    drift_z: float
    drift_flag: bool


class RankTurnover(BaseModel):
    mean_turnover: float
    max_turnover: float
    stable: bool


class DriftDiagnostics(BaseModel):
    drift_window: int
    baseline_days: int
    factor_drift: list[FactorDrift]
    coverage_drift: CoverageDrift
    rank_turnover: RankTurnover


class SignalEvaluation(BaseModel):
    eval_version: str
    start_date: str
    end_date: str
    forward_days: int
    trading_days_evaluated: int
    symbols: list[str]
    ic_report: ICReport | None
    drift_diagnostics: DriftDiagnostics | None


class SignalEvaluateResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: SignalEvaluation
    warnings: list[dict]
    errors: list[dict]


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


class PipelineCompareReturnMetricValue(BaseModel):
    cumulative_return: float
    win_rate: float
    max_drawdown: float
    annualized_volatility: float
    sharpe: float


class PipelineCompareReturnMetricDiff(BaseModel):
    excess_cumulative_return_v1_1_vs_v1: float
    excess_sharpe_v1_1_vs_v1: float


class PipelineCompareReturnMetrics(BaseModel):
    v1: PipelineCompareReturnMetricValue
    v1_1: PipelineCompareReturnMetricValue
    diff: PipelineCompareReturnMetricDiff


class PipelineCompareDailyReturnPoint(BaseModel):
    as_of: str
    top1_next_day_return: float


class PipelineCompareDailyReturnSeries(BaseModel):
    v1: list[PipelineCompareDailyReturnPoint]
    v1_1: list[PipelineCompareDailyReturnPoint]


class PipelineCompareGroupMetricValue(BaseModel):
    cumulative_return: float
    win_rate: float
    sharpe: float


class PipelineCompareGroupMetricDiff(BaseModel):
    excess_cumulative_return: float
    excess_sharpe: float


class PipelineCompareGroupStabilityItem(BaseModel):
    industry: str
    market_cap_bucket: str
    sample_days: int
    v1: PipelineCompareGroupMetricValue
    v1_1: PipelineCompareGroupMetricValue
    diff: PipelineCompareGroupMetricDiff
    stability_flag: Literal["OK", "LOW_SAMPLE"]


class PipelineCompareGroupStability(BaseModel):
    group_key: Literal["industry_market_cap_bucket"]
    items: list[PipelineCompareGroupStabilityItem]


class PipelineCompareAnalytics(BaseModel):
    return_metrics: PipelineCompareReturnMetrics
    daily_return_series: PipelineCompareDailyReturnSeries
    group_stability: PipelineCompareGroupStability


class PipelineCompareData(BaseModel):
    start_date: str
    end_date: str
    top_n: int
    score_versions: list[str]
    daily_items: list[PipelineCompareDailyItem]
    summary: PipelineCompareSummary
    analytics: PipelineCompareAnalytics


class DailyRunData(BaseModel):
    as_of: str
    skipped: bool | None = None
    skip_reason: str | None = None
    data_manifest_id: str | None = None
    factor_snapshot: FactorSnapshot | None = None
    execution_plan: ExecutionPlan | None = None
    l2_decision: L2Decision | None = None
    signal_matrix: SignalMatrix | None = None
    portfolio: dict | None = None
    risk_gate: dict | None = None
    pretrade: dict | None = None
    technical: TechnicalIndicators | None = None


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


class PortfolioOptimizeRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
    alpha: dict[str, float] | None = Field(
        default=None,
        description="标的 alpha 字典 {symbol: value}；缺省时自动从 L3 signal snapshot 取 composite_score",
    )
    prev_weights: dict[str, float] | None = Field(
        default=None,
        description="上期权重 {symbol: weight}；缺省时视为全零向量（首次运行）",
    )
    lambda_risk: float = Field(default=1.0, gt=0, description="风险厌恶系数，默认 1.0")
    lambda_tc: float = Field(default=0.001, ge=0, description="交易成本系数，默认 0.001")
    w_max: float = Field(default=0.30, gt=0, le=1.0, description="单标的权重上限，默认 0.30")
    ind_max: float = Field(default=0.40, gt=0, le=1.0, description="单行业权重上限，默认 0.40")
    lookback_days: int = Field(default=60, ge=20, le=252, description="协方差计算窗口（日历天），默认 60")


class PortfolioTargetWeightRow(BaseModel):
    symbol: str
    weight: float
    prev_weight: float
    delta: float


class PortfolioOptimizationReport(BaseModel):
    objective_value: float
    risk_contribution: float
    turnover_cost: float
    solver: str
    solve_time_ms: int


class PortfolioOptimizeData(BaseModel):
    as_of: str
    optimize_version: str
    optimization_status: str
    fallback_reason: str | None
    target_weights: list[PortfolioTargetWeightRow]
    optimization_report: PortfolioOptimizationReport


class PortfolioOptimizeResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: PortfolioOptimizeData
    warnings: list[dict]
    errors: list[dict]


class RiskCheckRequest(BaseModel):
    as_of: str = Field(description="计算基准日期，格式 YYYY-MM-DD（PIT 语义）")
    target_weights: dict[str, float] = Field(
        description="目标权重 {symbol: weight}，由 L4 portfolio optimize 输出"
    )
    prev_weights: dict[str, float] | None = Field(
        default=None,
        description="上期权重 {symbol: weight}；缺省时视为从零建仓（换手率 = 1.0）",
    )


class RiskCheckItem(BaseModel):
    name: str
    value: float
    threshold: float
    passed: bool


class RiskCheckData(BaseModel):
    as_of: str
    risk_gate: str
    regime: str
    regime_vol: float | None
    regime_vol_source: str
    checks: list[RiskCheckItem]
    block_codes: list[str]


class RiskCheckResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: RiskCheckData
    warnings: list[dict]
    errors: list[dict]


class ExecutionPlanRequest(BaseModel):
    as_of: str = Field(description="截面日期 YYYY-MM-DD（PIT）")
    target_weights: dict[str, float] = Field(description="L4 目标权重 {symbol: weight}")
    pretrade: dict | None = Field(
        default=None,
        description="L5.5 pretrade 响应中的 data（用于按 symbol 透传 impact_bp）；可空",
    )
    notional: float | None = Field(
        default=None,
        description="组合名义资金（CNY）；缺省 1_000_000，须与 pretrade 一致",
    )


class PretradeCheckRequest(BaseModel):
    as_of: str = Field(description="计算基准日期 YYYY-MM-DD（PIT）")
    target_weights: dict[str, float] = Field(description="目标权重 {symbol: weight}")
    notional: float | None = Field(
        default=None,
        description="组合名义资金（CNY）；缺省 1_000_000",
    )


class PretradeOrderRow(BaseModel):
    symbol: str
    target_weight: float
    target_notional: float
    adv: float
    participation_rate: float
    sigma: float
    impact_bp: float
    tradable: bool


class PretradeCheckData(BaseModel):
    as_of: str
    notional: float
    overall_tradable: bool
    total_impact_bp: float
    orders: list[PretradeOrderRow]


class PretradeCheckResponse(BaseModel):
    schema_version: str
    command: str
    run_id: str
    status: str
    generated_at: str
    source: str
    advice_only: bool
    decision_weight: int
    data: PretradeCheckData
    warnings: list[dict]
    errors: list[dict]
