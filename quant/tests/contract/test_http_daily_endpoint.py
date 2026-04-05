from unittest.mock import patch

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
    assert payload["data"]["factor_snapshot"]["snapshot_version"] == "l2-basic-v1.1"
    assert "execution_plan" in payload["data"]
    assert "technical" in payload["data"]
    tech = payload["data"]["technical"]
    assert tech is None or (
        isinstance(tech, dict) and "ma5_ma10" in tech and isinstance(tech["ma5_ma10"], dict)
    )


def test_http_daily_response_schema_includes_l2_decision() -> None:
    """验证 HTTP 响应 schema 包含 l2_decision 且类型正确"""
    app = create_app()
    client = TestClient(app)

    resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})

    assert resp.status_code == 200
    payload = resp.json()
    assert "technical" in payload["data"]
    assert "l2_decision" in payload["data"]
    l2d = payload["data"]["l2_decision"]
    assert l2d["score_version"] == "l2-score-v1.1"
    assert isinstance(l2d["universe_size"], int)
    assert isinstance(l2d["top_candidates"], list)
    assert isinstance(l2d["score_breakdown"], list)
    assert isinstance(l2d["factor_availability"], list)
    scores = [c["score"] for c in l2d["top_candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_daily_skips_non_trading_day():
    """非交易日（周日）返回 skipped=true，不触发任何计算"""
    app = create_app()
    client = TestClient(app)

    with patch("application.daily_run_service.is_sse_trading_day", return_value=False):
        resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-05"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline daily"
    assert payload["data"]["as_of"] == "2026-04-05"
    assert payload["data"]["skipped"] is True
    assert payload["data"]["skip_reason"] == "non_trading_day"
    assert "factor_snapshot" not in payload["data"]
