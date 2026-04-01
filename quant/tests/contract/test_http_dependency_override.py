from fastapi.testclient import TestClient

from interfaces.http.app import create_app
from interfaces.http.dependencies import get_daily_run_service


def _stub_daily_run_service(as_of: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": "run_stub",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {"as_of": as_of, "data_manifest_id": "dm_stub", "execution_plan": {"orders": []}},
        "warnings": [],
        "errors": [],
    }


def test_http_dependency_override_for_daily_service():
    app = create_app()
    app.dependency_overrides[get_daily_run_service] = lambda: _stub_daily_run_service
    client = TestClient(app)

    resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["run_id"] == "run_stub"
    assert payload["data"]["data_manifest_id"] == "dm_stub"
