"""HTTP routes for G2 experiment config snapshots (Phase 1 audit)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from interfaces.http.dependencies import (
    ExperimentConfigGetFn,
    ExperimentConfigListFn,
    ExperimentConfigSnapshotFn,
    get_experiment_config_get_fn,
    get_experiment_config_list_fn,
    get_experiment_config_snapshot_fn,
)

router = APIRouter(prefix="/api/v1/experiment", tags=["experiment"])


class ExperimentConfigSnapshotBody(BaseModel):
    note: str = Field(default="", description="可选备注，写入快照行")


@router.post(
    "/config/snapshot",
    summary="写入当前硬编码参数快照",
    response_description="CLI Output Schema 信封，command 为 hf config snapshot",
)
def post_experiment_config_snapshot(
    body: ExperimentConfigSnapshotBody | None = None,
    fn: ExperimentConfigSnapshotFn = Depends(get_experiment_config_snapshot_fn),
) -> JSONResponse:
    note = body.note if body else ""
    return JSONResponse(content=fn(note))


@router.get(
    "/configs",
    summary="列出历史参数快照",
    response_description="CLI Output Schema 信封，command 为 hf config list",
)
def get_experiment_config_list(
    layer: str | None = Query(default=None, description="仅保留含该 layer 行的 config_id"),
    limit: int = Query(default=20, ge=1, le=200),
    fn: ExperimentConfigListFn = Depends(get_experiment_config_list_fn),
) -> JSONResponse:
    return JSONResponse(content=fn(layer, limit))


@router.get(
    "/configs/{config_id}",
    summary="按 config_id 查询快照明细",
    response_description="CLI Output Schema 信封，command 为 hf config get；404=CONFIG_NOT_FOUND",
)
def get_experiment_config_by_id(
    config_id: str,
    fn: ExperimentConfigGetFn = Depends(get_experiment_config_get_fn),
) -> JSONResponse:
    payload = fn(config_id)
    if payload.get("status") == "error":
        code = None
        for err in payload.get("errors") or []:
            code = err.get("code")
            break
        if code == "CONFIG_NOT_FOUND":
            return JSONResponse(status_code=404, content=payload)
        if code == "EXPERIMENT_CONFIG_NO_DB":
            return JSONResponse(status_code=503, content=payload)
        return JSONResponse(status_code=500, content=payload)
    return JSONResponse(content=payload)
