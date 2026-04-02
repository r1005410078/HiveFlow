from __future__ import annotations

from datetime import datetime, timezone

from application.factor_optimization.analysis_service import analyze_factors
from application.factor_optimization.recommendation_service import suggest_weight_schemes


def _to_correlation_pairs(correlation_matrix: dict[str, dict[str, float]]) -> dict[tuple[str, str], float]:
    pairs: dict[tuple[str, str], float] = {}
    names = list(correlation_matrix.keys())
    for i, left in enumerate(names):
        for right in names[i + 1:]:
            pairs[(left, right)] = float(correlation_matrix.get(left, {}).get(right, 0.0))
    return pairs


def run_factor_optimization(
    start_date: str,
    end_date: str,
    factor_names: list[str],
    constraints: dict[str, float] | None = None,
    bar_store=None,
) -> dict:
    if start_date > end_date:
        raise ValueError("start_date must be on or before end_date")

    bars: list[dict] = []
    if bar_store is not None:
        bars = bar_store.list_bars(
            symbols=None,
            timeframe="1d",
            start_date=start_date,
            end_date=end_date,
            limit=200000,
        )

    analysis = analyze_factors(bars=bars, factor_names=factor_names, forward_days=1)
    health = analysis.get("factor_health", [])
    metrics = {
        item["factor_name"]: {
            "ic": float(item.get("ic", 0.0)),
            "sharpe": float(item.get("sharpe", 0.0)),
            "max_drawdown": float(item.get("max_drawdown", 0.2)),
        }
        for item in health
    }
    recommendations = suggest_weight_schemes(
        metrics=metrics,
        correlation_pairs=_to_correlation_pairs(analysis.get("correlation_matrix", {})),
        constraints=constraints or {},
    )
    return build_factor_optimization_report(
        start_date=start_date,
        end_date=end_date,
        factor_names=factor_names,
        analysis=analysis,
        recommendations=recommendations,
    )


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
