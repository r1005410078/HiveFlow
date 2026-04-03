from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    SignalSnapshotService,
    get_signal_snapshot_service,
)
from interfaces.http.schemas import (
    SignalSnapshotRequest,
    SignalSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


@router.post(
    "/snapshot",
    summary="获取 L3 信号快照",
    description=(
        "对指定日期计算标准化信号矩阵（去极值 + zscore + 等权聚合），"
        "返回 signal_matrix 含 rows、composite_scores、transform_stats。"
    ),
    response_description="L3 信号快照，含标准化信号与诊断指标",
)
def post_signal_snapshot(
    req: SignalSnapshotRequest,
    service: SignalSnapshotService = Depends(get_signal_snapshot_service),
) -> SignalSnapshotResponse:
    return SignalSnapshotResponse.model_validate(service(req.as_of))
