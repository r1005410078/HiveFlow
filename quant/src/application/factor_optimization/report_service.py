from __future__ import annotations

from datetime import datetime, timezone

from application.factor_optimization.correlation_alert_service import build_correlation_alerts
from application.factor_optimization.analysis_service import analyze_factors
from application.factor_optimization.combination_service import suggest_top_combinations
from application.factor_optimization.recommendation_service import suggest_weight_schemes
from application.factor_optimization.release_gate_service import build_release_gate
from application.factor_optimization.report_10d_service import build_report_10d


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
    correlation_threshold: float = 0.7,
    combination_size_min: int = 2,
    combination_size_max: int = 4,
    top_k_combinations: int = 5,
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
    constraint_map = dict(constraints or {})
    correlation_threshold = float(constraint_map.pop("__correlation_threshold__", correlation_threshold))
    combination_size_min = int(constraint_map.pop("__combination_size_min__", combination_size_min))
    combination_size_max = int(constraint_map.pop("__combination_size_max__", combination_size_max))
    top_k_combinations = int(constraint_map.pop("__top_k_combinations__", top_k_combinations))
    recommendations = suggest_weight_schemes(
        metrics=metrics,
        correlation_pairs=_to_correlation_pairs(analysis.get("correlation_matrix", {})),
        constraints=constraint_map,
    )
    return build_factor_optimization_report(
        start_date=start_date,
        end_date=end_date,
        factor_names=factor_names,
        analysis=analysis,
        recommendations=recommendations,
        correlation_threshold=correlation_threshold,
        combination_size_min=combination_size_min,
        combination_size_max=combination_size_max,
        top_k_combinations=top_k_combinations,
    )


def build_factor_optimization_report(
    start_date: str,
    end_date: str,
    factor_names: list[str],
    analysis: dict,
    recommendations: list[dict],
    correlation_threshold: float = 0.7,
    combination_size_min: int = 2,
    combination_size_max: int = 4,
    top_k_combinations: int = 5,
) -> dict:
    metrics = {
        item["factor_name"]: {
            "ic": float(item.get("ic", 0.0)),
            "sharpe": float(item.get("sharpe", 0.0)),
            "max_drawdown": float(item.get("max_drawdown", 0.2)),
        }
        for item in analysis.get("factor_health", [])
    }
    correlation_analysis = build_correlation_alerts(
        correlation_matrix=analysis.get("correlation_matrix", {}),
        metrics=metrics,
        threshold=correlation_threshold,
    )
    report = build_report_10d(
        factor_names=factor_names,
        analysis=analysis,
        recommendations=recommendations,
        correlation_analysis=correlation_analysis,
    )
    top_combinations = suggest_top_combinations(
        factor_names=factor_names,
        metrics=metrics,
        correlation_matrix=analysis.get("correlation_matrix", {}),
        correlation_threshold=correlation_threshold,
        combination_size_min=combination_size_min,
        combination_size_max=combination_size_max,
        top_k=top_k_combinations,
    )
    release_gate = build_release_gate(
        coverage=analysis.get("coverage", {}),
        correlation_analysis=correlation_analysis,
        top_combinations=top_combinations,
    )

    return {
        "schema_version": "1.0.0",
        "command": "hf factor optimize",
        "status": "ok",
        "advice_only": True,
        "decision_weight": 0,
        "data": {
            "factor_names": factor_names,
            "analysis": analysis,
            "correlation_analysis": correlation_analysis,
            "recommendations": recommendations,
            "recommended_scheme": recommendations[0]["name"] if recommendations else None,
            "report": report,
            "top_combinations": top_combinations,
            "release_gate": release_gate,
        },
        "audit": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_period": {"start_date": start_date, "end_date": end_date},
            "g3_review_required": True,
        },
        "warnings": [],
        "errors": [],
    }
