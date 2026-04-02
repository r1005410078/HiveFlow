from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_post_daily_contract():
    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline daily"
    assert payload["data"]["as_of"] == "2026-04-01"
    assert "data_manifest_id" in payload["data"]
    assert "factor_snapshot" in payload["data"]
    assert payload["data"]["factor_snapshot"]["factor_version"] == "l2-basic-v1"
    assert "execution_plan" in payload["data"]
