"""Aggregated read-only diagnostics for `hf doctor` (DB / sync / positions)."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any, Protocol


class _DoctorBarStorePort(Protocol):
    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]: ...

    def get_positions_detail(self, as_of: str) -> dict[str, Any]: ...


PRODUCER_VERSION = "quant-system-doctor-v1"


def _today_as_of() -> str:
    return date.today().isoformat()


def _latest_run_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row.get("run_id"),
        "status": row.get("status"),
        "started_at": row.get("started_at"),
        "finished_at": row.get("finished_at"),
        "timeframe": row.get("timeframe"),
        "effective_symbols_count": row.get("effective_symbols_count"),
        "written_rows": row.get("written_rows"),
        "end_date": row.get("end_date"),
    }


def run_system_doctor(
    *,
    bar_store: _DoctorBarStorePort | None,
    sync_days: int = 7,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Build server-side payload merged under CLI `data.quant` (not a full envelope)."""
    as_of_eff = as_of or _today_as_of()
    empty_sync = {
        "window_days": sync_days,
        "runs_returned": 0,
        "by_status": {},
        "latest": None,
        "has_running": False,
    }
    empty_positions = {
        "snapshot_as_of": None,
        "symbol_count": 0,
        "total_notional": 0.0,
        "has_positions": False,
        "error": None,
    }

    if bar_store is None:
        return {
            "producer_version": PRODUCER_VERSION,
            "db": {"reachable": False, "error": "NO_DB_CONFIG"},
            "sync": empty_sync,
            "positions": empty_positions,
        }

    try:
        runs = bar_store.list_sync_runs(days=sync_days, limit=50)
    except Exception as exc:  # noqa: BLE001 — aggregate diagnostic must not raise
        return {
            "producer_version": PRODUCER_VERSION,
            "db": {"reachable": False, "error": str(exc)},
            "sync": empty_sync,
            "positions": empty_positions,
        }

    by_status = Counter(str(r.get("status") or "") for r in runs)
    latest = _latest_run_summary(runs[0]) if runs else None
    has_running = any(str(r.get("status")) == "running" for r in runs)

    try:
        detail = bar_store.get_positions_detail(as_of_eff)
        notionals_raw = detail.get("notionals") or {}
        notionals = {str(k): float(v) for k, v in notionals_raw.items()}
        snap_date = detail.get("snapshot_as_of")
        if snap_date is not None:
            snap_date = str(snap_date)
    except Exception as exc:  # noqa: BLE001
        return {
            "producer_version": PRODUCER_VERSION,
            "db": {"reachable": True, "error": None},
            "sync": {
                "window_days": sync_days,
                "runs_returned": len(runs),
                "by_status": dict(by_status),
                "latest": latest,
                "has_running": has_running,
            },
            "positions": {
                "snapshot_as_of": None,
                "symbol_count": 0,
                "total_notional": 0.0,
                "has_positions": False,
                "error": str(exc),
            },
        }

    total_notional = float(sum(notionals.values())) if notionals else 0.0

    return {
        "producer_version": PRODUCER_VERSION,
        "db": {"reachable": True, "error": None},
        "sync": {
            "window_days": sync_days,
            "runs_returned": len(runs),
            "by_status": dict(by_status),
            "latest": latest,
            "has_running": has_running,
        },
        "positions": {
            "snapshot_as_of": snap_date,
            "symbol_count": len(notionals),
            "total_notional": total_notional,
            "has_positions": len(notionals) > 0,
            "error": None,
        },
    }
