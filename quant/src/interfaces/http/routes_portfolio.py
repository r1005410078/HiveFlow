from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    PortfolioOptimizeService,
    get_portfolio_optimize_service,
)
from interfaces.http.schemas import (
    PortfolioOptimizeRequest,
    PortfolioOptimizeResponse,
)

router = APIRouter(prefix="/api/v1/portfolio", tags=["portfolio"])


@router.post(
    "/optimize",
    summary="L4 组合优化（均值-方差 QP）",
    description=(
        "对指定日期计算目标权重。目标函数：max αᵀw - λ_risk·wᵀΣw - λ_tc·Σ|wᵢ-w_prev_i|，"
        "含单标的上限、行业上限约束。协方差从 DB bar 数据计算（需服务端已连接 DB）。"
        "alpha 缺省时自动从 L3 signal snapshot 取 composite_score。"
    ),
    response_description="目标权重 + 优化报告（含求解状态、风险贡献、换手成本）",
)
def post_portfolio_optimize(
    req: PortfolioOptimizeRequest,
    service: PortfolioOptimizeService = Depends(get_portfolio_optimize_service),
) -> PortfolioOptimizeResponse:
    return PortfolioOptimizeResponse.model_validate(
        service(
            req.as_of,
            req.alpha,
            req.prev_weights,
            req.lambda_risk,
            req.lambda_tc,
            req.w_max,
            req.ind_max,
            req.lookback_days,
        )
    )
