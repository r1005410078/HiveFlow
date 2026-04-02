from __future__ import annotations


def _factor_score(metrics: dict[str, dict[str, float]], factor_name: str) -> float:
    item = metrics.get(factor_name, {})
    return float(item.get("ic", 0.0)) + float(item.get("sharpe", 0.0))


def _choose_weaker_factor(
    left: str,
    right: str,
    metrics: dict[str, dict[str, float]],
) -> str:
    left_score = _factor_score(metrics, left)
    right_score = _factor_score(metrics, right)
    return right if left_score >= right_score else left


def build_correlation_alerts(
    correlation_matrix: dict[str, dict[str, float]],
    metrics: dict[str, dict[str, float]],
    threshold: float = 0.7,
) -> dict:
    if threshold <= 0 or threshold > 1:
        raise ValueError("correlation_threshold must be in (0, 1]")

    factor_names = list(correlation_matrix.keys())
    alerts: list[dict] = []

    for index, factor_a in enumerate(factor_names):
        for factor_b in factor_names[index + 1:]:
            correlation = float(correlation_matrix.get(factor_a, {}).get(factor_b, 0.0))
            abs_correlation = abs(correlation)
            if abs_correlation < threshold:
                continue

            weaker_factor = _choose_weaker_factor(factor_a, factor_b, metrics)
            severity = "high" if abs_correlation >= 0.8 else "medium"
            alerts.append(
                {
                    "factor_a": factor_a,
                    "factor_b": factor_b,
                    "correlation": round(correlation, 6),
                    "severity": severity,
                    "suggestion": f"consider reducing weight for {weaker_factor}",
                }
            )

    alerts.sort(key=lambda item: (-abs(item["correlation"]), item["factor_a"], item["factor_b"]))
    return {
        "threshold": threshold,
        "alerts": alerts,
        "alert_count": len(alerts),
    }
