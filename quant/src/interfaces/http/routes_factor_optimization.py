from fastapi import APIRouter, Depends, HTTPException

from interfaces.http.dependencies import (
    FactorOptimizationService,
    get_factor_optimization_service,
)
from interfaces.http.schemas import (
    FactorOptimizationEvaluateRequest,
    FactorOptimizationEvaluateResponse,
)


router = APIRouter(prefix="/api/v1/factor-optimization", tags=["factor-optimization"])


@router.post(
    "/evaluate",
    summary="运行因子评估与权重建议",
    description=(
        "基于历史 bars 计算因子健康度、相关性与权重建议。"
        "该接口仅输出建议，`advice_only=true` 且不会自动生效。"
    ),
)
def post_factor_optimization_evaluate(
    req: FactorOptimizationEvaluateRequest,
    service: FactorOptimizationService = Depends(get_factor_optimization_service),
) -> FactorOptimizationEvaluateResponse:
    try:
        if req.combination_size_min > req.combination_size_max:
            raise ValueError("combination_size_min must be on or below combination_size_max")
        constraints = dict(req.constraints)
        constraints["__correlation_threshold__"] = req.correlation_threshold
        constraints["__combination_size_min__"] = req.combination_size_min
        constraints["__combination_size_max__"] = req.combination_size_max
        constraints["__top_k_combinations__"] = req.top_k_combinations
        return FactorOptimizationEvaluateResponse.model_validate(
            service(
                start_date=req.start_date,
                end_date=req.end_date,
                factor_names=req.factor_names,
                constraints=constraints,
            )
        )
    except ValueError as exc:
        code = "INVALID_DATE_RANGE" if "start_date" in str(exc) else "INVALID_ARGUMENT"
        raise HTTPException(
            status_code=400,
            detail={
                "code": code,
                "message": str(exc),
            },
        ) from exc
