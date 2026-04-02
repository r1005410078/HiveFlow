from __future__ import annotations

from datetime import date, timedelta

from application.contracts.cli_output import ok_output
from application.daily_run_service import run_daily


_COMPARE_SCORE_VERSIONS = ("l2-score-v1", "l2-score-v1.1")


def _date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start_date must be on or before end_date")

    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def _extract_min_availability(l2_decision: dict) -> float:
    items = l2_decision.get("factor_availability", [])
    rates = [float(item.get("availability_rate", 0.0)) for item in items]
    return min(rates) if rates else 0.0


def _extract_top1_symbol(l2_decision: dict) -> str | None:
    candidates = l2_decision.get("top_candidates", [])
    if not candidates:
        return None
    return candidates[0].get("symbol")


def _run_version(
    as_of: str,
    version: str,
    root,
    bar_store,
    top_n: int,
    errors: list[dict],
) -> dict:
    try:
        out = run_daily(
            as_of=as_of,
            root=root,
            bar_store=bar_store,
            score_version=version,
            top_n=top_n,
        )
        warnings = out.get("warnings", [])
        l2_decision = out.get("data", {}).get("l2_decision", {})
        return {
            "score_version": version,
            "top_candidates": l2_decision.get("top_candidates", []),
            "warning_count": len(warnings),
            "min_availability": _extract_min_availability(l2_decision),
        }
    except Exception as exc:  # noqa: BLE001 - compare must keep running per-day.
        message = str(exc)
        errors.append(
            {
                "as_of": as_of,
                "score_version": version,
                "code": "PIPELINE_COMPARE_DAILY_FAILED",
                "message": message,
            }
        )
        return {
            "score_version": version,
            "top_candidates": [],
            "warning_count": 0,
            "min_availability": 0.0,
            "error": message,
        }


def run_pipeline_compare(
    start_date: str,
    end_date: str,
    top_n: int = 5,
    root=None,
    bar_store=None,
) -> dict:
    days = _date_range(start_date=start_date, end_date=end_date)
    errors: list[dict] = []
    daily_items: list[dict] = []
    warning_totals = {version: 0 for version in _COMPARE_SCORE_VERSIONS}
    min_availability_totals = {version: 0.0 for version in _COMPARE_SCORE_VERSIONS}
    top1_change_days = 0

    for as_of in days:
        v1 = _run_version(as_of, _COMPARE_SCORE_VERSIONS[0], root, bar_store, top_n, errors)
        v1_1 = _run_version(as_of, _COMPARE_SCORE_VERSIONS[1], root, bar_store, top_n, errors)
        daily_items.append({"as_of": as_of, "v1": v1, "v1_1": v1_1})

        warning_totals[_COMPARE_SCORE_VERSIONS[0]] += int(v1["warning_count"])
        warning_totals[_COMPARE_SCORE_VERSIONS[1]] += int(v1_1["warning_count"])
        min_availability_totals[_COMPARE_SCORE_VERSIONS[0]] += float(v1["min_availability"])
        min_availability_totals[_COMPARE_SCORE_VERSIONS[1]] += float(v1_1["min_availability"])
        if _extract_top1_symbol(v1) != _extract_top1_symbol(v1_1):
            top1_change_days += 1

    days_count = len(days)
    summary = {
        "days": days_count,
        "avg_warning_count_v1": round(warning_totals[_COMPARE_SCORE_VERSIONS[0]] / days_count, 6) if days_count else 0.0,
        "avg_warning_count_v1_1": round(warning_totals[_COMPARE_SCORE_VERSIONS[1]] / days_count, 6) if days_count else 0.0,
        "avg_min_availability_v1": round(min_availability_totals[_COMPARE_SCORE_VERSIONS[0]] / days_count, 6) if days_count else 0.0,
        "avg_min_availability_v1_1": round(min_availability_totals[_COMPARE_SCORE_VERSIONS[1]] / days_count, 6) if days_count else 0.0,
        "top1_symbol_change_days": top1_change_days,
    }

    return ok_output(
        command="hf pipeline compare",
        run_id=f"compare_{start_date.replace('-', '')}_{end_date.replace('-', '')}",
        data={
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
            "score_versions": list(_COMPARE_SCORE_VERSIONS),
            "daily_items": daily_items,
            "summary": summary,
        },
        warnings=[],
    ) | {"errors": errors}
