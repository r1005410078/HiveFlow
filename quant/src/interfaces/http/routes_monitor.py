"""HTTP routes for L8 monitor health report."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from interfaces.http.dependencies import HealthReportService, get_health_report_service

router = APIRouter(prefix="/v1/monitor", tags=["monitor"])


@router.get(
    "/health-report",
    summary="L8 因子/信号/风控健康报告",
    description="基于当日 `run_daily` 输出聚合健康度与 green/yellow/red 总评（纯消费层，不重复计算因子）。",
    response_description="标准 CLI Output Schema v1.0.0 信封，`command` 为 `hf monitor health-report`",
)
def get_health_report(
    as_of: str = Query(..., description="截面日期 YYYY-MM-DD"),
    service: HealthReportService = Depends(get_health_report_service),
) -> JSONResponse:
    raw = service(as_of)
    return JSONResponse(content=raw)
