from application.daily_run_service import run_daily


def test_daily_run_includes_l2_decision() -> None:
    """验证 daily 编排包含 l2_decision 输出"""
    result = run_daily(as_of="2026-04-01", root=None)

    assert "l2_decision" in result["data"]
    l2d = result["data"]["l2_decision"]

    assert l2d["score_version"] == "l2-score-v1.1"
    assert l2d["universe_size"] >= 0
    assert isinstance(l2d["top_candidates"], list)
    assert isinstance(l2d["score_breakdown"], list)
    assert isinstance(l2d["factor_availability"], list)

    scores = [c["score"] for c in l2d["top_candidates"]]
    assert scores == sorted(scores, reverse=True)


def test_daily_pipeline_end_to_end(tmp_path):
    """验证日频流水线输出包含 run_id、manifest_id、L2.1 因子快照与 execution_plan。"""
    out = run_daily(as_of="2026-04-01", root=tmp_path)
    assert out["status"] in {"ok", "warning"}
    assert out["run_id"].startswith("run_")
    assert "data_manifest_id" in out["data"]
    assert "factor_snapshot" in out["data"]
    assert out["data"]["factor_snapshot"]["factor_version"] == "l2-basic-v1.1"
    assert set(out["data"]["factor_snapshot"]["factor_names"]) >= {
        "max_drawdown_60",
        "trend_stability_20",
        "relative_strength_vs_index",
    }
    assert out["data"]["factor_snapshot"]["coverage_rate"] == 1.0
    assert "execution_plan" in out["data"]
    assert out["data"]["as_of"] == "2026-04-01"
    assert out["data"]["execution_plan"]["orders"] == []
