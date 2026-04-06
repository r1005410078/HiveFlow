"""Unit tests for `run_system_doctor`."""

from __future__ import annotations

from typing import Any

from application.system.doctor_service import run_system_doctor


class _FakeStore:
    def __init__(self, *, runs: list[dict], pos_detail: dict[str, Any]) -> None:
        self._runs = runs
        self._pos_detail = pos_detail

    def list_sync_runs(self, days: int, **kwargs: object) -> list[dict]:
        del days, kwargs
        return list(self._runs)

    def get_positions_detail(self, as_of: str) -> dict[str, Any]:
        del as_of
        return dict(self._pos_detail)


def test_no_db_config_returns_unreachable() -> None:
    out = run_system_doctor(bar_store=None, sync_days=7)
    assert out["db"]["reachable"] is False
    assert out["db"]["error"] == "NO_DB_CONFIG"
    assert out["sync"]["runs_returned"] == 0
    assert out["positions"]["has_positions"] is False


def test_with_runs_and_positions() -> None:
    runs = [
        {
            "run_id": "a",
            "status": "success",
            "started_at": "2026-04-01T00:00:00+00:00",
            "finished_at": "2026-04-01T01:00:00+00:00",
            "timeframe": "1d",
            "effective_symbols_count": 28,
            "written_rows": 100,
            "end_date": "2026-04-01",
        },
        {
            "run_id": "b",
            "status": "running",
            "started_at": "2026-04-02T00:00:00+00:00",
            "finished_at": None,
            "timeframe": "1d",
            "effective_symbols_count": 10,
            "written_rows": 0,
            "end_date": "2026-04-02",
        },
    ]
    pos = {
        "snapshot_as_of": "2026-04-01",
        "notionals": {"600519.SH": 100_000.0, "000001.SZ": 50_000.0},
    }
    out = run_system_doctor(bar_store=_FakeStore(runs=runs, pos_detail=pos), sync_days=7)
    assert out["db"]["reachable"] is True
    assert out["sync"]["runs_returned"] == 2
    assert out["sync"]["has_running"] is True
    assert out["sync"]["by_status"]["success"] == 1
    assert out["sync"]["by_status"]["running"] == 1
    assert out["sync"]["latest"]["run_id"] == "a"
    assert out["positions"]["symbol_count"] == 2
    assert out["positions"]["total_notional"] == 150_000.0
    assert out["positions"]["has_positions"] is True
    assert out["positions"]["snapshot_as_of"] == "2026-04-01"
