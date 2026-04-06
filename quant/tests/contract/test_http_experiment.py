"""Contract tests for G2 experiment config HTTP routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import (
    get_experiment_config_get_fn,
    get_experiment_config_list_fn,
    get_experiment_config_snapshot_fn,
)


def test_post_snapshot_ok() -> None:
    app = create_app()
    client = TestClient(app)

    def _snap(note: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "command": "hf config snapshot",
            "run_id": "cfg_stub",
            "status": "ok",
            "generated_at": "2026-04-01T10:00:00+00:00",
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "config_id": "uuid-here",
                "params_count": 33,
                "note": note,
                "created_at": "2026-04-01T10:00:00+00:00",
            },
            "warnings": [],
            "errors": [],
        }

    app.dependency_overrides[get_experiment_config_snapshot_fn] = lambda: (lambda n: _snap(n))
    try:
        resp = client.post("/api/v1/experiment/config/snapshot", json={"note": "t"})
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["params_count"] == 33
    assert body["data"]["note"] == "t"


def test_get_configs_ok() -> None:
    app = create_app()
    client = TestClient(app)

    def _list(layer: str | None, limit: int) -> dict:
        assert limit == 20
        return {
            "schema_version": "1.0.0",
            "command": "hf config list",
            "run_id": "cfg_list_stub",
            "status": "ok",
            "generated_at": "2026-04-01T10:00:00+00:00",
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {"configs": [{"config_id": "a", "params_count": 33, "note": None, "created_at": "x", "layers": ["l2"]}]},
            "warnings": [],
            "errors": [],
        }

    app.dependency_overrides[get_experiment_config_list_fn] = lambda: (lambda la, lim: _list(la, lim))
    try:
        resp = client.get("/api/v1/experiment/configs")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["data"]["configs"][0]["config_id"] == "a"


def test_get_config_detail_ok() -> None:
    app = create_app()
    client = TestClient(app)

    def _get(cid: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "command": "hf config get",
            "run_id": "cfg_get_stub",
            "status": "ok",
            "generated_at": "2026-04-01T10:00:00+00:00",
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "config_id": cid,
                "note": "n",
                "created_at": "2026-04-01T10:00:00+00:00",
                "params": [{"layer": "l5.5", "param_key": "eta", "param_value": 0.1}],
            },
            "warnings": [],
            "errors": [],
        }

    app.dependency_overrides[get_experiment_config_get_fn] = lambda: (lambda cid: _get(cid))
    try:
        resp = client.get("/api/v1/experiment/configs/abc-123")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert resp.json()["data"]["params"][0]["param_key"] == "eta"


def test_get_config_detail_404() -> None:
    app = create_app()
    client = TestClient(app)

    def _get(_cid: str) -> dict:
        return {
            "schema_version": "1.0.0",
            "command": "hf config get",
            "run_id": "cfg_get_stub",
            "status": "error",
            "generated_at": "2026-04-01T10:00:00+00:00",
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {},
            "warnings": [],
            "errors": [{"code": "CONFIG_NOT_FOUND", "message": "config_id not found"}],
        }

    app.dependency_overrides[get_experiment_config_get_fn] = lambda: (lambda cid: _get(cid))
    try:
        resp = client.get("/api/v1/experiment/configs/bad")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 404
    assert resp.json()["errors"][0]["code"] == "CONFIG_NOT_FOUND"
