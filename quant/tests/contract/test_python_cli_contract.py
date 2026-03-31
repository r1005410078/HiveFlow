from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_daily_contract_via_http():
    """验证 HTTP 日频接口输出符合基础 CLI 契约。"""
    client = TestClient(create_app())
    out = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})
    assert out.status_code == 200
    payload = out.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline daily"
    assert payload["data"]["as_of"] == "2026-04-01"
    assert "data_manifest_id" in payload["data"]
    assert "execution_plan" in payload["data"]
