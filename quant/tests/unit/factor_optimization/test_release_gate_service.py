from application.factor_optimization.release_gate_service import build_release_gate


def test_build_release_gate_returns_pass_when_metrics_healthy() -> None:
    gate = build_release_gate(
        coverage={"symbols": 20, "bars": 500},
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [],
            "alert_count": 0,
        },
        top_combinations={"items": [{"rank": 1, "factors": ["momentum_20", "inv_volatility_20"]}]},
    )

    assert gate["status"] == "pass"
    assert gate["blocking_reasons"] == []
    assert gate["watch_items"] == []


def test_build_release_gate_returns_watch_when_alerts_need_attention() -> None:
    gate = build_release_gate(
        coverage={"symbols": 20, "bars": 500},
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [],
            "alert_count": 2,
        },
        top_combinations={"items": [{"rank": 1, "factors": ["momentum_20", "inv_volatility_20"]}]},
    )

    assert gate["status"] == "watch"
    assert gate["blocking_reasons"] == []
    assert gate["watch_items"] == ["alert_count_watch:2"]


def test_build_release_gate_returns_watch_when_high_severity_alert_present() -> None:
    gate = build_release_gate(
        coverage={"symbols": 20, "bars": 500},
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [
                {
                    "factor_a": "momentum_20",
                    "factor_b": "inv_volatility_20",
                    "correlation": 0.82,
                    "severity": "high",
                    "suggestion": "reduce overlap",
                }
            ],
            "alert_count": 1,
        },
        top_combinations={"items": [{"rank": 1, "factors": ["momentum_20", "inv_volatility_20"]}]},
    )

    assert gate["status"] == "watch"
    assert gate["blocking_reasons"] == []
    assert gate["watch_items"] == ["high_correlation_alert_present"]


def test_build_release_gate_returns_fail_when_blockers_exist() -> None:
    gate = build_release_gate(
        coverage={"symbols": 19, "bars": 499},
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [],
            "alert_count": 4,
        },
        top_combinations={"items": []},
    )

    assert gate["status"] == "fail"
    assert gate["blocking_reasons"] == [
        "coverage_too_low",
        "alert_count_too_high:4",
        "no_top_combinations",
    ]
    assert gate["watch_items"] == []
