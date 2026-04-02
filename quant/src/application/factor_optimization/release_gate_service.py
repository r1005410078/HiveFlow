from __future__ import annotations


def build_release_gate(
    coverage: dict,
    correlation_analysis: dict,
    top_combinations: dict,
) -> dict:
    symbols = int((coverage or {}).get("symbols", 0))
    bars = int((coverage or {}).get("bars", 0))
    alert_count = int((correlation_analysis or {}).get("alert_count", 0))
    alerts = (correlation_analysis or {}).get("alerts") or []
    top_items = (top_combinations or {}).get("items") or []

    blocking_reasons: list[str] = []
    watch_items: list[str] = []

    if symbols < 20 or bars < 500:
        blocking_reasons.append("coverage_too_low")

    if alert_count >= 4:
        blocking_reasons.append(f"alert_count_too_high:{alert_count}")
    elif alert_count >= 2:
        watch_items.append(f"alert_count_watch:{alert_count}")

    if any(str(alert.get("severity", "")).lower() == "high" for alert in alerts):
        watch_items.append("high_correlation_alert_present")

    if not top_items:
        blocking_reasons.append("no_top_combinations")

    if blocking_reasons:
        status = "fail"
    elif watch_items:
        status = "watch"
    else:
        status = "pass"

    return {
        "status": status,
        "blocking_reasons": blocking_reasons,
        "watch_items": watch_items,
    }
