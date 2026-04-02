from __future__ import annotations

from datetime import datetime, timezone


def build_factor_optimization_report(
    start_date: str,
    end_date: str,
    factor_names: list[str],
    analysis: dict,
    recommendations: list[dict],
) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": "hf factor optimize",
        "status": "ok",
        "advice_only": True,
        "decision_weight": 0,
        "data": {
            "factor_names": factor_names,
            "analysis": analysis,
            "recommendations": recommendations,
            "recommended_scheme": recommendations[0]["name"] if recommendations else None,
        },
        "audit": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_period": {"start_date": start_date, "end_date": end_date},
            "g3_review_required": True,
        },
        "warnings": [],
        "errors": [],
    }
