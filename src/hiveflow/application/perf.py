# src/hiveflow/application/perf.py
"""实盘绩效追踪应用服务。"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Optional

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.portfolio_snapshots import PortfolioSnapshot

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(curve: list[float], width: int = 40) -> str:
    """将序列降采样到至多 width 个字符（与 cli.py 同算法的独立副本，无跨层依赖）。"""
    if not curve or len(curve) < 2:
        return "─" * width
    step = max(1, -(-len(curve) // width))
    sampled = [
        sum(curve[i: i + step]) / len(curve[i: i + step])
        for i in range(0, len(curve), step)
    ][:width]
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return _SPARK_CHARS[0] * len(sampled)
    bucket = (hi - lo) / (len(_SPARK_CHARS) - 1)
    return "".join(
        _SPARK_CHARS[min(int((v - lo) / bucket), len(_SPARK_CHARS) - 1)]
        for v in sampled
    )


def _compute_mdd(curve: list[float]) -> float:
    """从价值序列计算最大回撤（非正数）。"""
    if len(curve) < 2:
        return 0.0
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    return max_dd


@dataclass(frozen=True)
class PortfolioSnapshotView:
    id: int | None
    timestamp: str
    total_value_usd: float
    source: str
    notes: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "total_value_usd": self.total_value_usd,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PerfCompareResult:
    backtest_id: int
    live_sparkline: str
    backtest_sparkline: str
    live_total_return: float
    backtest_total_return: float
    live_annual_return: float | None    # None = 快照不足 2 条或 days==0
    backtest_annual_return: float | None
    live_mdd: float
    backtest_mdd: float
    snapshot_count: int

    def to_dict(self) -> dict:
        return {
            "backtest_id": self.backtest_id,
            "live_sparkline": self.live_sparkline,
            "backtest_sparkline": self.backtest_sparkline,
            "live_total_return": self.live_total_return,
            "backtest_total_return": self.backtest_total_return,
            "live_annual_return": self.live_annual_return,
            "backtest_annual_return": self.backtest_annual_return,
            "live_mdd": self.live_mdd,
            "backtest_mdd": self.backtest_mdd,
            "snapshot_count": self.snapshot_count,
        }


def record_snapshot(
    total_value_usd: float,
    positions_data: dict,
    source: str = "manual",
    notes: str | None = None,
    settings: Settings | None = None,
) -> PortfolioSnapshotView:
    """记录一次组合快照。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    snap = PortfolioSnapshot(
        total_value_usd=total_value_usd,
        positions_json=json.dumps(positions_data),
        source=source,
        notes=notes,
    )
    with get_session(app_settings) as session:
        session.add(snap)
        session.commit()
        session.refresh(snap)
        return _to_view(snap)


def list_snapshots(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[PortfolioSnapshotView]:
    """查询历史快照（最新在前）。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        rows = session.exec(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(limit)
        ).all()
        return [_to_view(r) for r in rows]


def compare_with_backtest(
    backtest_id: int,
    settings: Settings | None = None,
) -> PerfCompareResult:
    """对比实盘快照权益曲线与指定回测权益曲线，返回 Sparkline + 指标。"""
    from hiveflow.domain.backtests import BacktestResult

    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 加载回测
    with get_session(app_settings) as session:
        bt = session.get(BacktestResult, backtest_id)
        if bt is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        if bt.equity_curve is None:
            raise ValueError(f"回测 #{backtest_id} 无 equity_curve 数据，请重新运行回测。")
        backtest_curve: list[float] = json.loads(bt.equity_curve)

    # 加载快照（按时间升序）
    with get_session(app_settings) as session:
        snaps = session.exec(
            select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.asc())
        ).all()
        snaps = list(snaps)

    live_values = [s.total_value_usd for s in snaps]
    n_snaps = len(live_values)

    # 归一化实盘曲线到 1.0 起点
    if n_snaps >= 1:
        first_val = live_values[0]
        live_curve = [v / first_val for v in live_values] if first_val > 0 else live_values
    else:
        live_curve = [1.0]

    # 计算实盘指标
    if n_snaps >= 2:
        live_total_return = live_curve[-1] - 1.0
        days = (snaps[-1].timestamp - snaps[0].timestamp).days
        if days > 0:
            live_annual_return: Optional[float] = (1 + live_total_return) ** (365 / days) - 1
        else:
            live_annual_return = None
    else:
        live_total_return = 0.0
        live_annual_return = None

    live_mdd = _compute_mdd(live_curve)

    # 计算回测指标
    bt_total_return = backtest_curve[-1] / backtest_curve[0] - 1.0
    bt_mdd = _compute_mdd(backtest_curve)
    bt_days = len(backtest_curve) - 1
    if bt_days > 0:
        bt_annual_return: Optional[float] = (1 + bt_total_return) ** (365 / bt_days) - 1
    else:
        bt_annual_return = None

    return PerfCompareResult(
        backtest_id=backtest_id,
        live_sparkline=_sparkline(live_curve),
        backtest_sparkline=_sparkline(backtest_curve),
        live_total_return=live_total_return,
        backtest_total_return=bt_total_return,
        live_annual_return=live_annual_return,
        backtest_annual_return=bt_annual_return,
        live_mdd=live_mdd,
        backtest_mdd=bt_mdd,
        snapshot_count=n_snaps,
    )


def _to_view(snap: PortfolioSnapshot) -> PortfolioSnapshotView:
    return PortfolioSnapshotView(
        id=snap.id,
        timestamp=snap.timestamp.isoformat(),
        total_value_usd=snap.total_value_usd,
        source=snap.source,
        notes=snap.notes,
    )
