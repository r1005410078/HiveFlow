"""信号快照存储应用服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.signal_snapshots import SignalSnapshot
from hiveflow.domain.common import utc_now


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class SignalSnapshotHistoryView:
    id: int
    snapshot_id: str
    as_of: str
    symbol: str
    signals_count: int
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "as_of": self.as_of,
            "symbol": self.symbol,
            "signals_count": self.signals_count,
            "created_at": self.created_at,
        }


def save_signal_snapshot(payload: dict, settings: Settings | None = None) -> SignalSnapshotHistoryView:
    """落库一条 signal snapshot，并返回摘要视图。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    snapshot_id = payload.get("snapshot_id") or f"sig-{utc_now().strftime('%Y%m%d%H%M%S%f')}"
    as_of = _parse_iso_datetime(payload.get("as_of")) or utc_now()
    data_window = payload.get("data_window", {}) or {}
    row = SignalSnapshot(
        snapshot_id=snapshot_id,
        as_of=as_of,
        symbol=payload.get("symbol", "PORTFOLIO"),
        market=payload.get("market", "crypto"),
        feature_set_version=payload.get("feature_set_version"),
        style_preset_version=payload.get("style_preset_version"),
        symbols_hash=payload.get("symbols_hash"),
        params_hash=payload.get("params_hash"),
        code_version=payload.get("code_version"),
        signals_json=json.dumps(payload.get("signals", []), ensure_ascii=False),
        category_metrics_json=json.dumps(payload.get("category_metrics", {}), ensure_ascii=False),
        conflict_matrix_json=json.dumps(payload.get("conflict_matrix", []), ensure_ascii=False),
        data_window_start=_parse_iso_datetime(data_window.get("start")),
        data_window_end=_parse_iso_datetime(data_window.get("end")),
    )
    with get_session(app_settings) as session:
        session.add(row)
        session.commit()
        session.refresh(row)

    return SignalSnapshotHistoryView(
        id=row.id or 0,
        snapshot_id=row.snapshot_id,
        as_of=row.as_of.isoformat(),
        symbol=row.symbol,
        signals_count=len(payload.get("signals", [])),
        created_at=row.created_at.isoformat(),
    )


def list_signal_snapshots(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[SignalSnapshotHistoryView]:
    """按时间倒序列出信号快照。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        rows = session.exec(
            select(SignalSnapshot)
            .order_by(SignalSnapshot.created_at.desc())
            .limit(limit)
        ).all()

    result: list[SignalSnapshotHistoryView] = []
    for row in rows:
        signals = json.loads(row.signals_json)
        result.append(
            SignalSnapshotHistoryView(
                id=row.id or 0,
                snapshot_id=row.snapshot_id,
                as_of=row.as_of.isoformat(),
                symbol=row.symbol,
                signals_count=len(signals),
                created_at=row.created_at.isoformat(),
            )
        )
    return result


def get_signal_snapshot(record_id: int, settings: Settings | None = None) -> dict:
    """按记录 ID 读取完整快照。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)
    with get_session(app_settings) as session:
        row = session.get(SignalSnapshot, record_id)
        if row is None:
            raise ValueError(f"信号快照记录 #{record_id} 不存在。")

    return {
        "id": row.id,
        "snapshot_id": row.snapshot_id,
        "as_of": row.as_of.isoformat(),
        "symbol": row.symbol,
        "feature_set_version": row.feature_set_version,
        "style_preset_version": row.style_preset_version,
        "symbols_hash": row.symbols_hash,
        "params_hash": row.params_hash,
        "code_version": row.code_version,
        "signals": json.loads(row.signals_json),
        "category_metrics": json.loads(row.category_metrics_json),
        "conflict_matrix": json.loads(row.conflict_matrix_json),
        "data_window": {
            "start": row.data_window_start.isoformat() if row.data_window_start else None,
            "end": row.data_window_end.isoformat() if row.data_window_end else None,
        },
        "created_at": row.created_at.isoformat(),
    }
