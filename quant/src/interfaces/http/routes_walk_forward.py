"""HTTP routes for walk-forward backtest endpoint (L7)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from application.walk_forward_service import run_walk_forward

router = APIRouter(prefix="/v1/walk-forward", tags=["walk-forward"])


@router.post(
    "/run",
    summary="运行 walk-forward 回测（L7 验证层）",
    description=(
        "执行 walk-forward 回测：按参数定义生成滚动时间窗，"
        "每个窗口中执行日频策略流水线并计算收益率指标，"
        "最后按预设阈值门控检查。\n\n"
        "返回 verdict（pass/no_go）与各窗口及聚合结果。"
    ),
    response_model=None,
    responses={
        200: {"description": "回测完成，含 verdict 与结果"},
        422: {"description": "参数错误或日期范围无效"},
        503: {"description": "未配置数据库"},
    },
)
def post_walk_forward_run(
    start_date: str = Query(..., description="YYYY-MM-DD，回测期始"),
    end_date: str = Query(..., description="YYYY-MM-DD，回测期末"),
    warm_up_days: int = Query(default=180, ge=1, description="热身期日历天数"),
    test_window_days: int = Query(default=63, ge=1, description="测试窗口日历天数"),
    step_days: int = Query(default=21, ge=1, description="窗口滑动步长（日历天数）"),
    cost_bp: float = Query(default=0.0, ge=0.0, description="交易成本（基点）"),
) -> JSONResponse:
    """Run walk-forward backtest with specified parameters.

    Args:
        start_date: Start of backtest period (YYYY-MM-DD)
        end_date: End of backtest period (YYYY-MM-DD)
        warm_up_days: Calendar days for warm-up window
        test_window_days: Calendar days for test window
        step_days: Calendar days to step forward each window
        cost_bp: Transaction cost in basis points

    Returns:
        JSON response with verdict, windows, and aggregate metrics.

    Raises:
        HTTPException 503: If database not configured
        HTTPException 422: If parameters invalid or date range invalid
        HTTPException 500: For other errors
    """
    # Check if database is configured
    from interfaces.adapters.market_data.db_connection import has_db_config, open_db_connection_from_env
    from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore

    if not has_db_config():
        raise HTTPException(
            status_code=503,
            detail={"code": "WALK_FORWARD_DB_UNAVAILABLE", "message": "no database configured"},
        )

    # Create bar store
    try:
        bar_store = TimescaleBarStore(open_db_connection_from_env())
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "WALK_FORWARD_DB_UNAVAILABLE", "message": str(exc)},
        ) from exc

    # Run walk-forward backtest
    try:
        result = run_walk_forward(
            start_date=start_date,
            end_date=end_date,
            warm_up_days=warm_up_days,
            test_window_days=test_window_days,
            step_days=step_days,
            cost_bp=cost_bp,
            bar_store=bar_store,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "WALK_FORWARD_INVALID_PARAMS", "message": str(exc)},
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"code": "WALK_FORWARD_ERROR", "message": str(exc)},
        ) from exc

    # Wrap result in CLI output envelope
    return JSONResponse(
        status_code=200,
        content={
            "schema_version": "1.0.0",
            "command": "hf walk-forward run",
            "run_id": str(uuid4()),
            "status": "ok",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data": result,
        },
    )
