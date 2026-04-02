from application.decision.l2_decision_service import compute_l2_decision_from_snapshot


def _snapshot() -> dict:
    """标准测试数据：2 个标的，各 3 个因子完整"""
    return {
        "factor_version": "l2-basic-v1",
        "factor_names": ["momentum_20", "inv_volatility_20", "turnover_rate"],
        "coverage_rate": 1.0,
        "rows": [
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "momentum_20", "factor_version": "l2-basic-v1", "raw_value": 0.011},
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "inv_volatility_20", "factor_version": "l2-basic-v1", "raw_value": 1.1},
            {"as_of": "2026-04-01", "symbol": "000001.SZ", "factor_name": "turnover_rate", "factor_version": "l2-basic-v1", "raw_value": 0.006},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "momentum_20", "factor_version": "l2-basic-v1", "raw_value": 0.024},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "inv_volatility_20", "factor_version": "l2-basic-v1", "raw_value": 2.9},
            {"as_of": "2026-04-01", "symbol": "600519.SH", "factor_name": "turnover_rate", "factor_version": "l2-basic-v1", "raw_value": 0.019},
        ],
    }


def test_l2_decision_contains_explainable_fields() -> None:
    """验证输出结构完整性（包含版本信息）"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)

    assert out["schema_version"] == "1.0"
    assert out["score_version"] == "l2-score-v1"
    assert out["producer_version"] == "quant-l2"
    assert "generated_at" in out
    assert out["universe_size"] == 2

    assert out["top_candidates"][0]["symbol"] == "600519.SH"
    first = out["score_breakdown"][0]
    assert "symbol" in first
    assert {"final_score", "factors"} <= set(first.keys())
    assert {"factor_name", "raw_value", "normalized_value", "percentile", "clipped", "anomaly_flags", "weight", "contribution"} <= set(first["factors"][0].keys())


def test_l2_decision_is_deterministic_for_same_input() -> None:
    """验证确定性（相同输入产生相同输出）"""
    a = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    b = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    a_copy = {k: v for k, v in a.items() if k != "generated_at"}
    b_copy = {k: v for k, v in b.items() if k != "generated_at"}
    assert a_copy == b_copy


def test_l2_decision_percentile_in_valid_range() -> None:
    """验证分位数范围 (0, 1]"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    for item in out["score_breakdown"]:
        for factor in item["factors"]:
            percentile = factor["percentile"]
            assert 0 < percentile <= 1.0, f"percentile {percentile} out of range (0, 1]"


def test_l2_decision_with_missing_factor() -> None:
    """某标的某因子缺失时，用 0.0 填补并标记异常"""
    snapshot = _snapshot()
    snapshot["rows"] = [row for row in snapshot["rows"] if row["symbol"] != "600519.SH" or row["factor_name"] != "turnover_rate"]
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    breakdown_sh = [x for x in out["score_breakdown"] if x["symbol"] == "600519.SH"][0]
    turnover_factor = [f for f in breakdown_sh["factors"] if f["factor_name"] == "turnover_rate"][0]
    assert "missing_factor:turnover_rate" in turnover_factor["anomaly_flags"]
    assert turnover_factor["raw_value"] == 0.0


def test_l2_decision_with_empty_sample() -> None:
    """样本为空时返回空结果"""
    snapshot = _snapshot()
    snapshot["rows"] = []
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    assert out["universe_size"] == 0
    assert out["top_candidates"] == []
    assert out["score_breakdown"] == []


def test_l2_decision_with_flat_distribution() -> None:
    """某因子全样本同值时，标准化为 1.0、percentile=1.0 并标记异常"""
    snapshot = _snapshot()
    for row in snapshot["rows"]:
        if row["factor_name"] == "momentum_20":
            row["raw_value"] = 0.05
    out = compute_l2_decision_from_snapshot(snapshot, top_n=5)
    for item in out["score_breakdown"]:
        momentum = [f for f in item["factors"] if f["factor_name"] == "momentum_20"][0]
        assert momentum["normalized_value"] == 1.0
        assert momentum["percentile"] == 1.0
        assert "flat_distribution:momentum_20" in momentum["anomaly_flags"]


def test_l2_decision_contribution_sum_equals_final_score() -> None:
    """验证 sum(factors[].contribution) == final_score（6 位精度）"""
    out = compute_l2_decision_from_snapshot(_snapshot(), top_n=5)
    for item in out["score_breakdown"]:
        contribution_sum = sum(f["contribution"] for f in item["factors"])
        assert abs(contribution_sum - item["final_score"]) < 1e-6, (
            f"{item['symbol']}: sum(contribution)={contribution_sum} != final_score={item['final_score']}"
        )
