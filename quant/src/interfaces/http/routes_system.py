"""HTTP routes for system-level read-only diagnostics (`hf doctor` server aggregate)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from interfaces.http.dependencies import SystemDoctorEnvelopeFn, get_system_doctor_envelope

router = APIRouter(prefix="/v1/system", tags=["system"])


@router.get(
    "/doctor",
    summary="系统自检聚合（DB / 同步任务 / 持仓快照）",
    description=(
        "只读聚合：数据库连通、`sync_runs` 近窗摘要、`positions` 最新截面。"
        "供 CLI `hf doctor` 在 OpenAPI 探测成功后拉取；无 DB 时仍 200，`db.reachable=false`。"
    ),
    response_description="标准 CLI Output Schema v1.0.0 信封，`data` 为 quant 聚合体（CLI 侧写入 `data.quant`）",
)
def get_system_doctor(
    sync_days: int = Query(7, ge=1, le=90, description="统计 sync_runs 的回溯自然日窗"),
    service: SystemDoctorEnvelopeFn = Depends(get_system_doctor_envelope),
) -> JSONResponse:
    return JSONResponse(content=service(sync_days))
