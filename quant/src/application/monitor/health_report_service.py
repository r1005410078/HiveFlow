"""L8 health report: aggregate run_daily outputs into factor/signal/risk health + overall rating."""

from __future__ import annotations

import math
import statistics
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from application.contracts.cli_output import ok_output
from application.daily_run_service import run_daily


def _factor_item_status(rate: float) -> str:
    if rate >= 0.8:
        return "ok"
    if rate >= 0.5:
        return "warn"
    return "miss"


def _build_factor_health(l2_decision: dict[str, Any] | None) -> dict[str, Any]:
    items = (l2_decision or {}).get("factor_availability", [])
    details: list[dict[str, Any]] = []
    ok_c = warn_c = miss_c = 0
    for item in items:
        name = str(item.get("factor_name", ""))
        rate = float(item.get("availability_rate", 0.0))
        st = _factor_item_status(rate)
        if st == "ok":
            ok_c += 1
        elif st == "warn":
            warn_c += 1
        else:
            miss_c += 1
        details.append({"factor_name": name, "availability_rate": rate, "status": st})
    return {
        "total": len(items),
        "ok_count": ok_c,
        "warn_count": warn_c,
        "miss_count": miss_c,
        "details": details,
    }


def _build_signal_health(signal_matrix: dict[str, Any] | None) -> dict[str, Any]:
    if signal_matrix is None:
        return {
            "coverage_rate": 0.0,
            "composite_score_mean": 0.0,
            "composite_score_std": 0.0,
            "status": "miss",
        }
    coverage = float(signal_matrix.get("coverage_rate", 0.0))
    scores_raw: list[float] = []
    for cs in signal_matrix.get("composite_scores", []):
        try:
            v = float(cs["composite_score"])
        except (KeyError, TypeError, ValueError):
            continue
        if not math.isnan(v):
            scores_raw.append(v)
    mean_v = float(statistics.mean(scores_raw)) if scores_raw else 0.0
    std_v = float(statistics.pstdev(scores_raw)) if len(scores_raw) > 1 else 0.0
    if coverage >= 0.7:
        sig_status = "ok"
    elif coverage >= 0.5:
        sig_status = "warn"
    else:
        sig_status = "miss"
    return {
        "coverage_rate": coverage,
        "composite_score_mean": mean_v,
        "composite_score_std": std_v,
        "status": sig_status,
    }


def _build_risk_health(risk_gate: dict[str, Any] | None) -> dict[str, Any]:
    if risk_gate is None:
        return {"regime": "normal", "triggered_rules": [], "status": "ok"}
    regime = str(risk_gate.get("regime", "normal"))
    triggered = list(risk_gate.get("block_codes", []))
    if regime == "crisis":
        st = "crisis"
    elif regime == "warning" or len(triggered) > 0:
        st = "warn"
    else:
        st = "ok"
    return {"regime": regime, "triggered_rules": triggered, "status": st}


def _compute_overall_rating(
    factor_health: dict[str, Any],
    signal_health: dict[str, Any],
    risk_health: dict[str, Any],
    signal_matrix: dict[str, Any] | None,
) -> str:
    miss_count = int(factor_health["miss_count"])
    warn_count = int(factor_health["warn_count"])
    coverage = float(signal_health["coverage_rate"])
    regime = str(risk_health["regime"])
    triggered = risk_health["triggered_rules"]

    if (
        miss_count >= 1
        or regime == "crisis"
        or coverage < 0.5
        or signal_matrix is None
    ):
        return "red"
    if (
        warn_count >= 2
        or regime == "warning"
        or len(triggered) > 0
        or coverage < 0.7
    ):
        return "yellow"
    return "green"


def run_health_report(
    as_of: str,
    *,
    bar_store: Any = None,
    run_daily_fn: Callable[[str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    run_id = f"hr_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    runner = run_daily_fn or (lambda ao: run_daily(as_of=ao, root=None, bar_store=bar_store))

    try:
        daily = runner(as_of)
    except Exception as exc:  # noqa: BLE001 — L8 must not crash; surface as envelope
        return {
            "schema_version": "1.0.0",
            "command": "hf monitor health-report",
            "run_id": run_id,
            "status": "error",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "as_of": as_of,
                "overall_rating": "red",
                "factor_health": None,
                "signal_health": None,
                "risk_health": None,
                "trend": None,
                "run_daily_warnings": [],
            },
            "warnings": [],
            "errors": [
                {
                    "code": "HEALTH_REPORT_DAILY_FAILED",
                    "message": str(exc),
                }
            ],
        }

    if daily.get("data", {}).get("skipped"):
        dd = daily["data"]
        return ok_output(
            command="hf monitor health-report",
            run_id=run_id,
            data={
                "as_of": as_of,
                "skipped": True,
                "skip_reason": dd.get("skip_reason"),
                "overall_rating": None,
                "factor_health": None,
                "signal_health": None,
                "risk_health": None,
                "trend": None,
                "run_daily_warnings": daily.get("warnings", []),
            },
            warnings=[],
        )

    dd = daily["data"]
    l2 = dd.get("l2_decision")
    signal_matrix = dd.get("signal_matrix")
    risk_gate = dd.get("risk_gate")

    factor_health = _build_factor_health(l2 if isinstance(l2, dict) else None)
    signal_health = _build_signal_health(signal_matrix if isinstance(signal_matrix, dict) else None)
    risk_health = _build_risk_health(risk_gate if isinstance(risk_gate, dict) else None)
    sm_for_rating = signal_matrix if isinstance(signal_matrix, dict) else None
    overall = _compute_overall_rating(factor_health, signal_health, risk_health, sm_for_rating)

    return ok_output(
        command="hf monitor health-report",
        run_id=run_id,
        data={
            "as_of": dd.get("as_of", as_of),
            "overall_rating": overall,
            "factor_health": factor_health,
            "signal_health": signal_health,
            "risk_health": risk_health,
            "trend": None,
            "run_daily_warnings": daily.get("warnings", []),
        },
        warnings=[],
    )
