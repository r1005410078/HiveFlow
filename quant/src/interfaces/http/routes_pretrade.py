from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    PretradeService,
    get_pretrade_service,
)
from interfaces.http.schemas import (
    PretradeCheckRequest,
    PretradeCheckResponse,
)

router = APIRouter(prefix="/api/v1/pretrade", tags=["pretrade"])


@router.post(
    "/check",
    summary="L5.5 预交易冲击与可成交性估算",
    description=(
        "基于平方根市场冲击模型估算各标的 impact（bp）与参与度是否超过 10% ADV；"
        "不阻断 pipeline，供运营与 L6 参考。"
    ),
    response_description="统一 CLI 信封，data 含 orders 与 overall_tradable",
)
def post_pretrade_check(
    req: PretradeCheckRequest,
    service: PretradeService = Depends(get_pretrade_service),
) -> PretradeCheckResponse:
    return PretradeCheckResponse.model_validate(
        service(req.as_of, req.target_weights, req.notional)
    )
