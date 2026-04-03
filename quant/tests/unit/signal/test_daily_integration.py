from unittest.mock import patch

from application.daily_run_service import run_daily


def test_daily_pipeline_includes_signal_matrix():
    result = run_daily(as_of="2026-04-01", root=None)
    data = result["data"]
    assert "signal_matrix" in data
    sm = data["signal_matrix"]
    assert sm is not None
    assert sm["schema_version"] == "1.0"
    assert sm["signal_version"] == "l3-signal-v1.0"
    assert len(sm["rows"]) == 30
    assert len(sm["composite_scores"]) == 5


def test_daily_pipeline_signal_matrix_failure_resilient():
    with patch(
        "application.daily_run_service.compute_signal_matrix",
        side_effect=RuntimeError("boom"),
    ):
        result = run_daily(as_of="2026-04-01", root=None)
    assert result["status"] == "ok"
    assert result["data"]["signal_matrix"] is None
    warning_codes = [w["code"] for w in result["warnings"]]
    assert "SIGNAL_MATRIX_FAILED" in warning_codes
