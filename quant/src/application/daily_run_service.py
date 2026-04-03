import logging
from datetime import date, timedelta
from uuid import uuid4

from application.contracts.cli_output import ok_output
from application.decision.l2_decision_service import compute_l2_decision_from_snapshot
from application.factor.basic_factor_service import (
    compute_basic_factor_snapshot,
    compute_basic_factor_snapshot_from_bars,
)


_FACTOR_AVAILABILITY_WARN_THRESHOLD = 0.8
_BENCHMARK_SYMBOL = "000300.SH"

_logger = logging.getLogger(__name__)


def _build_factor_quality_warnings(l2_decision: dict) -> list[dict]:
    warnings: list[dict] = []
    for item in l2_decision.get("factor_availability", []):
        rate = float(item.get("availability_rate", 0.0))
        if rate < _FACTOR_AVAILABILITY_WARN_THRESHOLD:
            warnings.append(
                {
                    "code": "FACTOR_AVAILABILITY_LOW",
                    "message": (
                        f"factor {item.get('factor_name')} availability {rate:.4f} "
                        f"is below threshold {_FACTOR_AVAILABILITY_WARN_THRESHOLD:.2f}"
                    ),
                }
            )
    return warnings


def run_daily(
    as_of: str,
    root,
    bar_store=None,
    score_version: str = "l2-score-v1.1",
    top_n: int = 5,
) -> dict:
    # root 预留给后续持久化与工作目录上下文使用。
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    symbols = [
        "000001.SZ",
        "600519.SH",
        "300750.SZ",
        "601318.SH",
        "000333.SZ",
    ]
    # 默认先构造 deterministic 快照，保证无依赖场景也可稳定运行。
    factor_snapshot = compute_basic_factor_snapshot(as_of=as_of, symbols=symbols)
    if bar_store is not None:
        try:
            # 优先使用真实 bars 计算因子（近 180 天窗口，覆盖 60/20 日特征需求）。
            start_date = (date.fromisoformat(as_of) - timedelta(days=180)).isoformat()
            bar_rows = bar_store.list_bars(
                symbols=symbols,
                timeframe="1d",
                start_date=start_date,
                end_date=as_of,
                limit=10000,
            )
            # Query benchmark bars (need >= 21 bars; query 40 days to be safe)
            try:
                benchmark_start = (date.fromisoformat(as_of) - timedelta(days=60)).isoformat()
                benchmark_rows = bar_store.list_bars(
                    symbols=[_BENCHMARK_SYMBOL],
                    timeframe="1d",
                    start_date=benchmark_start,
                    end_date=as_of,
                    limit=60,
                )
            except Exception:
                benchmark_rows = None
            factor_snapshot = compute_basic_factor_snapshot_from_bars(
                as_of=as_of,
                symbols=symbols,
                bar_rows=bar_rows,
                benchmark_rows=benchmark_rows,
            )
        except Exception:
            # 保持流水线韧性：任何读取/计算异常都降级到 deterministic 快照，不阻断 daily。
            _logger.warning(
                "daily run: bar_store path failed; using deterministic factor snapshot",
                exc_info=True,
            )
    l2_decision = compute_l2_decision_from_snapshot(
        factor_snapshot=factor_snapshot,
        top_n=top_n,
        score_version=score_version,
    )
    warnings = _build_factor_quality_warnings(l2_decision)
    return ok_output(
        command="hf pipeline daily",
        run_id=run_id,
        data={
            "as_of": as_of,
            "data_manifest_id": f"dm_{as_of.replace('-', '')}_{str(uuid4())[:6]}",
            "factor_snapshot": factor_snapshot,
            "execution_plan": {"orders": []},
            "l2_decision": l2_decision,
        },
        warnings=warnings,
    )
