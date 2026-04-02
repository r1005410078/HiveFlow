from application.factor_optimization.release_gate_service import build_release_gate


def test_build_release_gate_returns_pass_when_metrics_healthy() -> None:
    gate = build_release_gate(
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [],
            "alert_count": 0,
        },
        report={
            "matrix_10d": [{"dimension": "IC", "status": "good"}],
            "summary": {"recommended_scheme": "balanced"},
            "g3_checklist": [
                {"item": "风控组评审", "checked": False},
                {"item": "合规组审核", "checked": False},
                {"item": "CRO 最终批准", "checked": False},
            ],
        },
    )

    assert gate["status"] == "pass"
    assert gate["blocking_reasons"] == []
    assert gate["watch_items"] == []


def test_build_release_gate_returns_fail_when_alerts_too_high() -> None:
    gate = build_release_gate(
        correlation_analysis={
            "threshold": 0.7,
            "alerts": [
                {
                    "factor_a": "momentum_20",
                    "factor_b": "max_drawdown_60",
                    "correlation": 0.82,
                    "severity": "high",
                    "suggestion": "reduce overlap",
                }
            ],
            "alert_count": 1,
        },
        report={
            "matrix_10d": [{"dimension": "Correlation Redundancy", "status": "blocked"}],
            "summary": {"recommended_scheme": "balanced"},
            "g3_checklist": [
                {"item": "风控组评审", "checked": False},
                {"item": "合规组审核", "checked": False},
                {"item": "CRO 最终批准", "checked": False},
            ],
        },
    )

    assert gate["status"] == "fail"
    assert gate["blocking_reasons"]
    assert gate["watch_items"]
