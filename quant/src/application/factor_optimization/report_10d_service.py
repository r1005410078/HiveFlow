from __future__ import annotations


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 6)


def _fmt_number(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def _fmt_ratio(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.4f}"


def _top_weight(recommendations: list[dict]) -> tuple[str | None, float | None]:
    if not recommendations:
        return None, None
    weights = recommendations[0].get("weights") or {}
    if not weights:
        return recommendations[0].get("name"), None
    factor_name, weight = max(weights.items(), key=lambda item: float(item[1]))
    return factor_name, float(weight)


def build_report_10d(
    factor_names: list[str],
    analysis: dict,
    recommendations: list[dict],
    correlation_analysis: dict,
) -> dict:
    factor_health = analysis.get("factor_health", [])
    coverage = analysis.get("coverage", {})
    avg_ic = _average([float(item.get("ic", 0.0)) for item in factor_health])
    avg_sharpe = _average([float(item.get("sharpe", 0.0)) for item in factor_health])
    avg_drawdown = _average([float(item.get("max_drawdown", 0.0)) for item in factor_health])
    alert_count = int(correlation_analysis.get("alert_count", 0))
    threshold = float(correlation_analysis.get("threshold", 0.7))
    recommendation_name = recommendations[0].get("name") if recommendations else None
    top_weight_factor, top_weight_value = _top_weight(recommendations)

    if recommendations and len(recommendations) > 1:
        incremental_value = round(
            float(recommendations[0].get("score", 0.0)) - float(recommendations[1].get("score", 0.0)),
            6,
        )
    else:
        incremental_value = None

    matrix_10d = [
        {
            "dimension": "IC",
            "value": _fmt_number(avg_ic),
            "status": "good" if avg_ic is not None and avg_ic >= 0 else "watch",
            "note": f"average across {len(factor_health)} factors",
        },
        {
            "dimension": "Sharpe",
            "value": _fmt_number(avg_sharpe),
            "status": "good" if avg_sharpe is not None and avg_sharpe >= 1.0 else "watch",
            "note": f"average across {len(factor_health)} factors",
        },
        {
            "dimension": "Max Drawdown",
            "value": _fmt_ratio(avg_drawdown),
            "status": "good" if avg_drawdown is not None and avg_drawdown <= 0.25 else "watch",
            "note": f"average across {len(factor_health)} factors",
        },
        {
            "dimension": "Correlation Redundancy",
            "value": f"{alert_count} alerts @ {threshold:.2f}",
            "status": "watch" if alert_count else "good",
            "note": "high correlation pairs above threshold",
        },
        {
            "dimension": "Coverage",
            "value": f"symbols={coverage.get('symbols', 0)}, bars={coverage.get('bars', 0)}",
            "status": "good" if coverage.get("symbols", 0) and coverage.get("bars", 0) else "watch",
            "note": f"factors={len(factor_names)}",
        },
        {
            "dimension": "Stability",
            "value": "N/A",
            "status": "unknown",
            "note": "window delta not computed in P1",
        },
        {
            "dimension": "Data Quality",
            "value": "N/A" if not factor_health else "basic checks passed",
            "status": "unknown" if not factor_health else "good",
            "note": "missing/anomaly detail is not yet surfaced",
        },
        {
            "dimension": "Risk Contribution",
            "value": "N/A" if top_weight_factor is None else f"{top_weight_factor}={_fmt_number(top_weight_value)}",
            "status": "unknown" if top_weight_factor is None else "good",
            "note": f"scheme={recommendation_name or 'N/A'}",
        },
        {
            "dimension": "Incremental Value",
            "value": "N/A" if incremental_value is None else _fmt_number(incremental_value),
            "status": "unknown" if incremental_value is None else "good",
            "note": "vs runner-up recommendation",
        },
        {
            "dimension": "Operational Readiness",
            "value": "G3 checklist required",
            "status": "blocked" if alert_count else "review",
            "note": "final approval handled outside the model",
        },
    ]

    if alert_count:
        key_findings = [f"correlation alerts: {alert_count}"]
    else:
        key_findings = ["no correlation alerts above threshold"]

    if recommendation_name:
        key_findings.append(f"recommended scheme: {recommendation_name}")

    return {
        "matrix_10d": matrix_10d,
        "summary": {
            "recommended_scheme": recommendation_name,
            "key_findings": key_findings,
        },
        "g3_checklist": [
            {"item": "风控组评审", "checked": False},
            {"item": "合规组审核", "checked": False},
            {"item": "CRO 最终批准", "checked": False},
        ],
    }
