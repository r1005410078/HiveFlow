from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    RiskCheckService,
    get_risk_check_service,
)
from interfaces.http.schemas import (
    RiskCheckRequest,
    RiskCheckResponse,
)

router = APIRouter(prefix="/api/v1/risk", tags=["risk"])


@router.post(
    "/check",
    summary="L5 风险门控检查",
    description=(
        "对 L4 目标权重执行风险硬约束检查。"
        "自动检测市场状态（normal/warning/crisis）并应用对应阈值，"
        "执行四项检查：组合年化波动率、单标的集中度、行业集中度、单日换手率。"
        "任意一项超阈值返回 risk_gate=block，status=warning。"
    ),
    response_description="风险门控结果，含市场状态、各项检查明细与拒单码",
)
def post_risk_check(
    req: RiskCheckRequest,
    service: RiskCheckService = Depends(get_risk_check_service),
) -> RiskCheckResponse:
    return RiskCheckResponse.model_validate(
        service(req.as_of, req.target_weights, req.prev_weights)
    )
