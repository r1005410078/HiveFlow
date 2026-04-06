"""HTTP routes for L6 execution plan (Phase 1: simulated orders)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from interfaces.http.dependencies import ExecutionPlanService, get_execution_service
from interfaces.http.schemas import ExecutionPlanRequest

router = APIRouter(prefix="/api/v1/execution", tags=["execution"])


@router.post(
    "/plan",
    summary="L6 执行计划（订单生成）",
    description=(
        "基于 L4 目标权重、L5.5 pretrade 与 DB 持仓快照生成限价日单计划；"
        "不接券商，仅供运营确认。"
    ),
    response_description="标准 CLI Output Schema v1.0.0 信封，`command` 为 `hf execution plan`",
)
def post_execution_plan(
    req: ExecutionPlanRequest,
    service: ExecutionPlanService = Depends(get_execution_service),
) -> JSONResponse:
    n = req.notional if req.notional is not None else 1_000_000.0
    raw = service(req.as_of, req.target_weights, req.pretrade, n)
    return JSONResponse(content=raw)
