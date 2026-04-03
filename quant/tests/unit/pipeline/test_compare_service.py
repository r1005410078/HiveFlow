import math

import pytest

from application.pipeline_compare_service import run_pipeline_compare


def _daily_run(
    as_of: str,
    score_version: str,
    top_candidates: list[dict],
    warnings: list[dict],
    availability: list[dict],
) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": f"run_{as_of}_{score_version}",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": as_of,
            "data_manifest_id": f"dm_{as_of}",
            "factor_snapshot": {
                "snapshot_version": "l2-basic-v1.1",
                "factor_names": ["momentum_20"],
                "coverage_rate": 1.0,
                "rows": [],
            },
            "execution_plan": {"orders": []},
            "l2_decision": {
                "schema_version": "1.0",
                "generated_at": "2026-04-01T00:00:00+00:00",
                "producer_version": "quant-l2",
                "score_version": score_version,
                "universe_size": 2,
                "top_candidates": top_candidates,
                "factor_availability": availability,
                "score_breakdown": [],
            },
        },
        "warnings": warnings,
        "errors": [],
    }


def test_compare_service_builds_daily_items_and_summary(monkeypatch) -> None:
    calls: list[tuple[str, str, int]] = []

    def fake_run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1", top_n: int = 5) -> dict:
        del root, bar_store
        calls.append((as_of, score_version, top_n))
        if score_version == "l2-score-v1":
            return _daily_run(
                as_of,
                score_version,
                top_candidates=[{"symbol": "000001.SZ", "score": 0.4, "rank": 1}],
                warnings=[{"code": "LOW"}],
                availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 1.0}],
            )
        return _daily_run(
            as_of,
            score_version,
            top_candidates=[{"symbol": "600519.SH", "score": 0.6, "rank": 1}],
            warnings=[],
            availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 0.5}],
        )

    monkeypatch.setattr("application.pipeline_compare_service.run_daily", fake_run_daily)

    out = run_pipeline_compare(start_date="2026-04-01", end_date="2026-04-02", top_n=5, root=None, bar_store=None)

    assert out["schema_version"] == "1.0.0"
    assert out["command"] == "hf pipeline compare"
    assert out["data"]["start_date"] == "2026-04-01"
    assert out["data"]["end_date"] == "2026-04-02"
    assert out["data"]["top_n"] == 5
    assert out["data"]["score_versions"] == ["l2-score-v1", "l2-score-v1.1"]
    assert len(out["data"]["daily_items"]) == 2
    assert out["data"]["daily_items"][0]["v1"]["top_candidates"][0]["symbol"] == "000001.SZ"
    assert out["data"]["daily_items"][0]["v1_1"]["top_candidates"][0]["symbol"] == "600519.SH"
    assert out["data"]["summary"]["days"] == 2
    assert out["data"]["summary"]["avg_warning_count_v1"] == 1.0
    assert out["data"]["summary"]["avg_warning_count_v1_1"] == 0.0
    assert out["data"]["summary"]["avg_min_availability_v1"] == 1.0
    assert out["data"]["summary"]["avg_min_availability_v1_1"] == 0.5
    assert out["data"]["summary"]["top1_symbol_change_days"] == 2
    assert calls == [
        ("2026-04-01", "l2-score-v1", 5),
        ("2026-04-01", "l2-score-v1.1", 5),
        ("2026-04-02", "l2-score-v1", 5),
        ("2026-04-02", "l2-score-v1.1", 5),
    ]


def test_compare_service_builds_return_metrics(monkeypatch) -> None:
    def fake_run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1", top_n: int = 5) -> dict:
        del root, bar_store, top_n
        top_candidates_by_day = {
            ("2026-04-01", "l2-score-v1"): [
                {
                    "symbol": "000001.SZ",
                    "score": 0.4,
                    "rank": 1,
                    "next_day_return": 0.02,
                }
            ],
            ("2026-04-01", "l2-score-v1.1"): [
                {
                    "symbol": "600519.SH",
                    "score": 0.6,
                    "rank": 1,
                    "next_day_return": 0.01,
                }
            ],
            ("2026-04-02", "l2-score-v1"): [
                {
                    "symbol": "000001.SZ",
                    "score": 0.45,
                    "rank": 1,
                    "next_day_return": -0.01,
                }
            ],
            ("2026-04-02", "l2-score-v1.1"): [
                {
                    "symbol": "600519.SH",
                    "score": 0.65,
                    "rank": 1,
                    "next_day_return": 0.03,
                }
            ],
        }
        return _daily_run(
            as_of,
            score_version,
            top_candidates=top_candidates_by_day[(as_of, score_version)],
            warnings=[],
            availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 1.0}],
        )

    monkeypatch.setattr("application.pipeline_compare_service.run_daily", fake_run_daily)

    out = run_pipeline_compare(start_date="2026-04-01", end_date="2026-04-02", top_n=5, root=None, bar_store=None)

    analytics = out["data"]["analytics"]
    daily_return_series = analytics["daily_return_series"]
    return_metrics = analytics["return_metrics"]

    assert {"return_metrics", "daily_return_series", "group_stability"} <= set(analytics.keys())
    assert {"v1", "v1_1", "diff"} <= set(return_metrics.keys())
    assert {
        "cumulative_return",
        "win_rate",
        "max_drawdown",
        "annualized_volatility",
        "sharpe",
    } <= set(return_metrics["v1"].keys())
    assert {"v1", "v1_1"} <= set(daily_return_series.keys())
    assert isinstance(daily_return_series["v1"], list)
    assert isinstance(daily_return_series["v1_1"], list)
    assert len(daily_return_series["v1"]) == 2
    assert len(daily_return_series["v1_1"]) == 2
    for series_key in ("v1", "v1_1"):
        for item in daily_return_series[series_key]:
            assert {"as_of", "top1_next_day_return"} <= set(item.keys())
    assert return_metrics["v1"]["cumulative_return"] == pytest.approx(0.0098)
    assert return_metrics["v1"]["win_rate"] == pytest.approx(0.5)
    assert return_metrics["v1_1"]["cumulative_return"] == pytest.approx(0.0403)
    assert return_metrics["v1_1"]["win_rate"] == pytest.approx(1.0)
    assert {"excess_cumulative_return_v1_1_vs_v1", "excess_sharpe_v1_1_vs_v1"} <= set(return_metrics["diff"].keys())
    assert return_metrics["diff"]["excess_cumulative_return_v1_1_vs_v1"] == pytest.approx(0.0305)
    assert isinstance(return_metrics["diff"]["excess_sharpe_v1_1_vs_v1"], float)


def test_compare_service_builds_group_stability_by_industry_and_market_cap_bucket(monkeypatch) -> None:
    def fake_run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1", top_n: int = 5) -> dict:
        del root, bar_store, top_n
        top_candidates_by_day = {
            ("2026-04-01", "l2-score-v1"): [
                {
                    "symbol": "000001.SZ",
                    "score": 0.4,
                    "rank": 1,
                    "industry": "Bank",
                    "market_cap_bucket": "LARGE",
                    "next_day_return": 0.02,
                }
            ],
            ("2026-04-01", "l2-score-v1.1"): [
                {
                    "symbol": "600519.SH",
                    "score": 0.6,
                    "rank": 1,
                    "industry": "Bank",
                    "market_cap_bucket": "LARGE",
                    "next_day_return": 0.01,
                }
            ],
            ("2026-04-02", "l2-score-v1"): [
                {
                    "symbol": "300750.SZ",
                    "score": 0.45,
                    "rank": 1,
                    "industry": "Tech",
                    "market_cap_bucket": "MID",
                    "next_day_return": -0.01,
                }
            ],
            ("2026-04-02", "l2-score-v1.1"): [
                {
                    "symbol": "002594.SZ",
                    "score": 0.65,
                    "rank": 1,
                    "industry": "Tech",
                    "market_cap_bucket": "MID",
                    "next_day_return": 0.03,
                }
            ],
            ("2026-04-03", "l2-score-v1"): [
                {
                    "symbol": "688111.SH",
                    "score": 0.5,
                    "rank": 1,
                    "industry": "Tech",
                    "market_cap_bucket": "MID",
                    "next_day_return": 0.02,
                }
            ],
            ("2026-04-03", "l2-score-v1.1"): [
                {
                    "symbol": "601398.SH",
                    "score": 0.66,
                    "rank": 1,
                    "industry": "Bank",
                    "market_cap_bucket": "LARGE",
                    "next_day_return": 0.01,
                }
            ],
        }
        return _daily_run(
            as_of,
            score_version,
            top_candidates=top_candidates_by_day[(as_of, score_version)],
            warnings=[],
            availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 1.0}],
        )

    monkeypatch.setattr("application.pipeline_compare_service.run_daily", fake_run_daily)

    out = run_pipeline_compare(start_date="2026-04-01", end_date="2026-04-03", top_n=5, root=None, bar_store=None)

    group_stability = out["data"]["analytics"]["group_stability"]

    assert group_stability["group_key"] == "industry_market_cap_bucket"
    assert {"group_key", "items"} <= set(group_stability.keys())
    assert isinstance(group_stability["items"], list)
    assert len(group_stability["items"]) == 2
    expected = {
        ("Bank", "LARGE"): {
            "sample_days": 1,
            "stability_flag": "LOW_SAMPLE",
            "v1_cumulative_return": 0.02,
            "v1_1_cumulative_return": 0.01,
        },
        ("Tech", "MID"): {
            "sample_days": 1,
            "stability_flag": "LOW_SAMPLE",
            "v1_cumulative_return": -0.01,
            "v1_1_cumulative_return": 0.03,
        },
    }
    for item in group_stability["items"]:
        assert {
            "industry",
            "market_cap_bucket",
            "sample_days",
            "v1",
            "v1_1",
            "diff",
            "stability_flag",
        } <= set(item.keys())
        key = (item["industry"], item["market_cap_bucket"])
        assert key in expected
        assert item["sample_days"] == expected[key]["sample_days"]
        assert item["stability_flag"] == expected[key]["stability_flag"]
        assert item["v1"]["cumulative_return"] == pytest.approx(expected[key]["v1_cumulative_return"])
        assert item["v1_1"]["cumulative_return"] == pytest.approx(expected[key]["v1_1_cumulative_return"])


def test_compare_service_filters_non_finite_returns_and_aligns_diff_metrics(monkeypatch) -> None:
    def fake_run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1", top_n: int = 5) -> dict:
        del root, bar_store, top_n
        top_candidates_by_day = {
            ("2026-04-01", "l2-score-v1"): [
                {"symbol": "000001.SZ", "score": 0.4, "rank": 1, "next_day_return": float("nan")}
            ],
            ("2026-04-01", "l2-score-v1.1"): [
                {"symbol": "600519.SH", "score": 0.6, "rank": 1, "next_day_return": 0.05}
            ],
            ("2026-04-02", "l2-score-v1"): [
                {"symbol": "000001.SZ", "score": 0.45, "rank": 1, "next_day_return": 0.02}
            ],
            ("2026-04-02", "l2-score-v1.1"): [
                {"symbol": "600519.SH", "score": 0.65, "rank": 1, "next_day_return": float("inf")}
            ],
            ("2026-04-03", "l2-score-v1"): [
                {"symbol": "000001.SZ", "score": 0.5, "rank": 1, "next_day_return": 0.01}
            ],
            ("2026-04-03", "l2-score-v1.1"): [
                {"symbol": "600519.SH", "score": 0.7, "rank": 1, "next_day_return": 0.03}
            ],
        }
        return _daily_run(
            as_of,
            score_version,
            top_candidates=top_candidates_by_day[(as_of, score_version)],
            warnings=[],
            availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 1.0}],
        )

    monkeypatch.setattr("application.pipeline_compare_service.run_daily", fake_run_daily)

    out = run_pipeline_compare(start_date="2026-04-01", end_date="2026-04-03", top_n=5, root=None, bar_store=None)

    analytics = out["data"]["analytics"]
    daily_return_series = analytics["daily_return_series"]
    return_metrics = analytics["return_metrics"]

    assert [item["as_of"] for item in daily_return_series["v1"]] == ["2026-04-02", "2026-04-03"]
    assert [item["as_of"] for item in daily_return_series["v1_1"]] == ["2026-04-01", "2026-04-03"]
    assert return_metrics["v1"]["cumulative_return"] == pytest.approx(0.0302)
    assert return_metrics["v1_1"]["cumulative_return"] == pytest.approx(0.0815)
    assert return_metrics["diff"]["excess_cumulative_return_v1_1_vs_v1"] == pytest.approx(0.02)
    assert return_metrics["diff"]["excess_sharpe_v1_1_vs_v1"] == pytest.approx(0.0)

    for metric_group in (return_metrics["v1"], return_metrics["v1_1"], return_metrics["diff"]):
        for value in metric_group.values():
            assert math.isfinite(value)


def test_compare_service_records_failed_day_and_continues(monkeypatch) -> None:
    def fake_run_daily(as_of: str, root, bar_store=None, score_version: str = "l2-score-v1.1", top_n: int = 5) -> dict:
        del root, bar_store, top_n
        if as_of == "2026-04-02" and score_version == "l2-score-v1":
            raise RuntimeError("boom")
        return _daily_run(
            as_of,
            score_version,
            top_candidates=[{"symbol": f"{score_version}:{as_of}", "score": 0.6, "rank": 1}],
            warnings=[],
            availability=[{"factor_name": "momentum_20", "present_count": 1, "missing_count": 0, "availability_rate": 1.0}],
        )

    monkeypatch.setattr("application.pipeline_compare_service.run_daily", fake_run_daily)

    out = run_pipeline_compare(start_date="2026-04-01", end_date="2026-04-02", top_n=5, root=None, bar_store=None)

    assert len(out["data"]["daily_items"]) == 2
    assert out["data"]["daily_items"][1]["v1"]["top_candidates"] == []
    assert out["data"]["daily_items"][1]["v1"]["error"] == "boom"
    assert out["data"]["summary"]["days"] == 2
    assert out["errors"]


def test_compare_service_rejects_inverted_date_range() -> None:
    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        run_pipeline_compare(start_date="2026-04-02", end_date="2026-04-01", top_n=5, root=None, bar_store=None)
