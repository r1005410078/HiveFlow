"""Contract tests for GET /v1/system/doctor."""

from __future__ import annotations

from fastapi.testclient import TestClient

from application.system.doctor_service import run_system_doctor
from interfaces.http.app import create_app
from interfaces.http.dependencies import get_system_doctor_envelope


def _stub_envelope(sync_days: int) -> dict:
    payload = run_system_doctor(bar_store=None, sync_days=sync_days)
    return {
        "schema_version": "1.0.0",
        "command": "hf doctor",
        "run_id": "test-run",
        "status": "ok",
        "generated_at": "2026-04-06T12:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": payload,
        "warnings": [],
        "errors": [],
    }


def test_get_system_doctor_ok() -> None:
    app = create_app()
    app.dependency_overrides[get_system_doctor_envelope] = lambda: _stub_envelope
    with TestClient(app) as client:
        resp = client.get("/v1/system/doctor", params={"sync_days": 7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["command"] == "hf doctor"
    assert body["data"]["db"]["reachable"] is False
    assert body["data"]["sync"]["window_days"] == 7


def test_get_system_doctor_sync_days_clamped_422() -> None:
    app = create_app()
    app.dependency_overrides[get_system_doctor_envelope] = lambda: _stub_envelope
    with TestClient(app) as client:
        resp = client.get("/v1/system/doctor", params={"sync_days": 0})
    assert resp.status_code == 422
