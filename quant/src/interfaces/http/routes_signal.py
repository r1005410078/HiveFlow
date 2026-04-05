from fastapi import APIRouter, Depends

from interfaces.http.dependencies import (
    SignalEvaluateService,
    SignalSnapshotService,
    get_signal_evaluate_service,
    get_signal_snapshot_service,
)
from interfaces.http.schemas import (
    SignalEvaluateRequest,
    SignalEvaluateResponse,
    SignalSnapshotRequest,
    SignalSnapshotResponse,
)

router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


@router.post(
    "/snapshot",
    summary="获取 L3 信号快照",
    description=(
        "对指定日期计算标准化信号矩阵（去极值 + zscore + 等权聚合）。"
        "响应 `data` 含 `signal_matrix`（rows、composite_scores、transform_stats）"
        "与可选 `technical.ma5_ma10`（有 bar 数据时 MA5/MA10 金叉死叉；否则 `technical` 为 null）。"
    ),
    response_description="L3 信号快照，含标准化信号与诊断指标",
)
def post_signal_snapshot(
    req: SignalSnapshotRequest,
    service: SignalSnapshotService = Depends(get_signal_snapshot_service),
) -> SignalSnapshotResponse:
    return SignalSnapshotResponse.model_validate(service(req.as_of))


@router.post(
    "/evaluate",
    summary="L3 信号质量评估（IC + 漂移检测）",
    description=(
        "对指定日期范围逐日重算 L3 信号，计算 Rank IC（per-factor + composite）"
        "和信号分布漂移诊断。需要 DB 中的真实 bar 数据。"
    ),
    response_description="IC 报告 + 漂移诊断",
)
def post_signal_evaluate(
    req: SignalEvaluateRequest,
    service: SignalEvaluateService = Depends(get_signal_evaluate_service),
) -> SignalEvaluateResponse:
    return SignalEvaluateResponse.model_validate(
        service(req.start_date, req.end_date, req.forward_days)
    )
