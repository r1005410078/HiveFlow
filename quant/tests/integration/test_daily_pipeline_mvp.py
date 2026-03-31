from application.daily_run_service import run_daily


def test_daily_pipeline_end_to_end(tmp_path):
    """验证日频流水线输出包含 run_id、manifest_id 与 execution_plan。"""
    out = run_daily(as_of="2026-04-01", root=tmp_path)
    assert out["status"] in {"ok", "warning"}
    assert out["run_id"].startswith("run_")
    assert "data_manifest_id" in out["data"]
    assert "execution_plan" in out["data"]
    assert out["data"]["as_of"] == "2026-04-01"
    assert out["data"]["execution_plan"]["orders"] == []
