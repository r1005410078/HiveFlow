from fastapi import APIRouter, Depends, HTTPException
from interfaces.http.dependencies import (
    DailyRunService,
    PipelineCompareService,
    get_daily_run_service,
    get_pipeline_compare_service,
)
from interfaces.http.mapper import to_daily_input
from interfaces.http.schemas import (
    DailyRunRequest,
    DailyRunResponse,
    PipelineCompareRequest,
    PipelineCompareResponse,
)

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post(
    "/daily",
    summary="运行日频策略流水线",
    description=(
        "触发指定日期的完整日频流水线，依次执行：\n\n"
        "1. **L1 因子计算**：计算 6 因子快照（`momentum_20`、`inv_volatility_20`、`turnover_rate`、"
        "`max_drawdown_60`、`trend_stability_20`、`relative_strength_vs_index`）\n"
        "2. **L2 候选排名**：对标的池打分并输出 Top-5 可解释候选，含 `score_breakdown`\n"
        "3. **执行计划**：生成订单列表（当前 Phase 1 为空数组）\n\n"
        "响应遵循 CLI Output Schema v1.0.0，`data.l2_decision` 含完整打分明细。"
    ),
    response_description="日频流水线完整输出，含因子快照、L2 候选排名与执行计划",
    responses={
        200: {
            "description": "流水线执行成功",
            "content": {
                "application/json": {
                    "example": {
                        "schema_version": "1.0.0",
                        "command": "hf pipeline daily",
                        "run_id": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "ok",
                        "generated_at": "2026-04-01T09:00:00+08:00",
                        "source": "system",
                        "advice_only": False,
                        "decision_weight": 1,
                        "data": {
                            "as_of": "2026-04-01",
                            "data_manifest_id": "manifest_20260401",
                            "factor_snapshot": {
                                "snapshot_version": "l2-basic-v1.1",
                                "factor_names": [
                                    "momentum_20",
                                    "inv_volatility_20",
                                    "turnover_rate",
                                    "max_drawdown_60",
                                    "trend_stability_20",
                                    "relative_strength_vs_index",
                                ],
                                "coverage_rate": 1.0,
                                "rows": [
                                    {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "momentum_20",
                                     "factor_version": "l2-momentum-v1.0", "raw_value": 0.024,
                                     "direction": 1, "unit": "return", "missing_strategy": "deterministic_fallback",
                                     "source": "real"},
                                ],
                            },
                            "l2_decision": {
                                "schema_version": "1.0",
                                "generated_at": "2026-04-01T09:00:00+00:00",
                                "producer_version": "quant-l2",
                                "score_version": "l2-score-v1.1",
                                "universe_size": 2,
                                "top_candidates": [
                                    {"symbol": "600519.SH", "score": 0.812300, "rank": 1},
                                    {"symbol": "000001.SZ", "score": 0.423100, "rank": 2},
                                ],
                                "factor_availability": [
                                    {
                                        "factor_name": "momentum_20",
                                        "present_count": 2,
                                        "missing_count": 0,
                                        "availability_rate": 1.0,
                                    }
                                ],
                                "score_breakdown": [
                                    {
                                        "symbol": "600519.SH",
                                        "final_score": 0.812300,
                                        "factors": [
                                            {
                                                "factor_name": "momentum_20",
                                                "raw_value": 0.024,
                                                "normalized_value": 1.0,
                                                "percentile": 1.0,
                                                "clipped": False,
                                                "anomaly_flags": [],
                                                "weight": 0.5,
                                                "contribution": 0.5,
                                            }
                                        ],
                                    }
                                ],
                            },
                            "execution_plan": {"orders": []},
                        },
                        "warnings": [],
                        "errors": [],
                    }
                }
            },
        }
    },
)
def post_daily(
    req: DailyRunRequest,
    service: DailyRunService = Depends(get_daily_run_service),
) -> DailyRunResponse:
    data = to_daily_input(req)
    return DailyRunResponse.model_validate(service(data["as_of"]))


@router.post(
    "/compare",
    summary="运行版本对比回放",
    description=(
        "在指定日期区间内对比 `l2-score-v1` 与 `l2-score-v1.1` 的逐日候选结果与数据质量指标，"
        "并返回 `json/table` 复用的输出合同。"
    ),
    response_description="版本对比回放输出，含逐日明细与汇总统计",
)
def post_compare(
    req: PipelineCompareRequest,
    service: PipelineCompareService = Depends(get_pipeline_compare_service),
) -> PipelineCompareResponse:
    try:
        return PipelineCompareResponse.model_validate(service(req.start_date, req.end_date, req.top_n))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_DATE_RANGE",
                "message": str(exc),
            },
        ) from exc
