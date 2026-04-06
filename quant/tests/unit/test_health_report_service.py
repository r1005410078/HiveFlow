from application.monitor.health_report_service import run_health_report


def _envelope_base(as_of: str, *, data: dict) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": "run_daily_stub",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": data,
        "warnings": [],
        "errors": [],
    }


def _daily_all_green(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [
                    {"factor_name": "momentum_20", "availability_rate": 0.95},
                    {"factor_name": "inv_volatility_20", "availability_rate": 0.9},
                ],
            },
            "signal_matrix": {
                "coverage_rate": 0.85,
                "composite_scores": [
                    {"symbol": "600519.SH", "composite_score": 0.1},
                    {"symbol": "000001.SZ", "composite_score": 0.2},
                ],
            },
            "risk_gate": {
                "regime": "normal",
                "block_codes": [],
            },
        },
    )


def test_overall_green_all_ok() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_all_green)
    assert out["status"] == "ok"
    d = out["data"]
    assert d["overall_rating"] == "green"
    assert d["factor_health"]["ok_count"] == 2
    assert d["signal_health"]["status"] == "ok"
    assert d["risk_health"]["status"] == "ok"
    assert d["trend"] is None
    assert d["run_daily_warnings"] == []


def _daily_two_factor_warns(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [
                    {"factor_name": "a", "availability_rate": 0.9},
                    {"factor_name": "b", "availability_rate": 0.65},
                    {"factor_name": "c", "availability_rate": 0.6},
                ],
            },
            "signal_matrix": {"coverage_rate": 0.75, "composite_scores": []},
            "risk_gate": {"regime": "normal", "block_codes": []},
        },
    )


def test_overall_yellow_two_factor_warns() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_two_factor_warns)
    assert out["data"]["overall_rating"] == "yellow"
    fh = out["data"]["factor_health"]
    assert fh["warn_count"] == 2


def _daily_one_miss(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [
                    {"factor_name": "ok_f", "availability_rate": 0.9},
                    {"factor_name": "miss_f", "availability_rate": 0.4},
                ],
            },
            "signal_matrix": {"coverage_rate": 0.9, "composite_scores": []},
            "risk_gate": {"regime": "normal", "block_codes": []},
        },
    )


def test_overall_red_one_factor_miss() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_one_miss)
    assert out["data"]["overall_rating"] == "red"


def _daily_crisis(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [
                    {"factor_name": "x", "availability_rate": 0.9},
                ],
            },
            "signal_matrix": {"coverage_rate": 0.85, "composite_scores": []},
            "risk_gate": {"regime": "crisis", "block_codes": []},
        },
    )


def test_overall_red_regime_crisis() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_crisis)
    assert out["data"]["overall_rating"] == "red"
    assert out["data"]["risk_health"]["status"] == "crisis"


def _daily_signal_low(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [{"factor_name": "x", "availability_rate": 0.9}],
            },
            "signal_matrix": {"coverage_rate": 0.4, "composite_scores": []},
            "risk_gate": {"regime": "normal", "block_codes": []},
        },
    )


def test_overall_red_signal_coverage_low() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_signal_low)
    assert out["data"]["overall_rating"] == "red"


def _daily_no_signal_matrix(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [{"factor_name": "x", "availability_rate": 0.9}],
            },
            "risk_gate": {"regime": "normal", "block_codes": []},
        },
    )


def test_signal_matrix_null_is_miss_and_red() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_no_signal_matrix)
    assert out["data"]["signal_health"]["status"] == "miss"
    assert out["data"]["overall_rating"] == "red"


def _daily_no_risk_gate(as_of: str) -> dict:
    return _envelope_base(
        as_of,
        data={
            "as_of": as_of,
            "l2_decision": {
                "factor_availability": [{"factor_name": "x", "availability_rate": 0.9}],
            },
            "signal_matrix": {"coverage_rate": 0.85, "composite_scores": []},
        },
    )


def test_risk_gate_null_loose_ok() -> None:
    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_daily_no_risk_gate)
    assert out["data"]["risk_health"]["status"] == "ok"
    assert out["data"]["overall_rating"] == "green"


def test_run_daily_exception_returns_red_envelope() -> None:
    def _boom(_: str) -> dict:
        raise RuntimeError("boom")

    out = run_health_report("2026-04-01", bar_store=None, run_daily_fn=_boom)
    assert out["status"] == "error"
    assert out["errors"]
    assert out["data"]["overall_rating"] == "red"


def _daily_skipped(as_of: str) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf pipeline daily",
        "run_id": "run_skip",
        "status": "ok",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {
            "as_of": as_of,
            "skipped": True,
            "skip_reason": "non_trading_day",
        },
        "warnings": [],
        "errors": [],
    }


def test_non_trading_skipped() -> None:
    out = run_health_report("2026-04-06", bar_store=None, run_daily_fn=_daily_skipped)
    assert out["status"] == "ok"
    assert out["data"]["skipped"] is True
    assert out["data"]["overall_rating"] is None
    assert out["data"]["factor_health"] is None
