from __future__ import annotations

import math
from datetime import date, timedelta

from application.contracts.cli_output import ok_output
from application.daily_run_service import run_daily


_COMPARE_SCORE_VERSIONS = ("l2-score-v1", "l2-score-v1.1")
_ANNUALIZATION_DAYS = 252
_GROUP_STABILITY_KEY = "industry_market_cap_bucket"
_LOW_SAMPLE_DAYS = 5


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


def _extract_top1_candidate(version_result: dict) -> dict | None:
    candidates = version_result.get("top_candidates", [])
    if not candidates:
        return None
    return candidates[0]


def _extract_top1_next_day_return(version_result: dict) -> float | None:
    top_candidate = _extract_top1_candidate(version_result)
    if top_candidate is None:
        return None
    value = top_candidate.get("next_day_return")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round_metric(value: float) -> float:
    return round(float(value), 6)


def _build_return_metrics(returns: list[float]) -> dict:
    if not returns:
        return {
            "cumulative_return": 0.0,
            "win_rate": 0.0,
            "max_drawdown": 0.0,
            "annualized_volatility": 0.0,
            "sharpe": 0.0,
        }

    equity_curve = 1.0
    peak = 1.0
    max_drawdown = 0.0
    wins = 0

    for daily_return in returns:
        equity_curve *= 1.0 + daily_return
        peak = max(peak, equity_curve)
        if peak > 0:
            max_drawdown = max(max_drawdown, (peak - equity_curve) / peak)
        if daily_return > 0:
            wins += 1

    mean_return = sum(returns) / len(returns)
    if len(returns) > 1:
        variance = sum((daily_return - mean_return) ** 2 for daily_return in returns) / (len(returns) - 1)
        annualized_volatility = math.sqrt(variance) * math.sqrt(_ANNUALIZATION_DAYS)
    else:
        annualized_volatility = 0.0

    sharpe = 0.0 if annualized_volatility == 0.0 else (mean_return * _ANNUALIZATION_DAYS) / annualized_volatility

    return {
        "cumulative_return": _round_metric(equity_curve - 1.0),
        "win_rate": _round_metric(wins / len(returns)),
        "max_drawdown": _round_metric(max_drawdown),
        "annualized_volatility": _round_metric(annualized_volatility),
        "sharpe": _round_metric(sharpe),
    }


def _build_daily_return_series(daily_items: list[dict]) -> dict:
    series = {"v1": [], "v1_1": []}
    for daily_item in daily_items:
        for version_key in ("v1", "v1_1"):
            top1_next_day_return = _extract_top1_next_day_return(daily_item[version_key])
            if top1_next_day_return is None:
                continue
            series[version_key].append(
                {
                    "as_of": daily_item["as_of"],
                    "top1_next_day_return": _round_metric(top1_next_day_return),
                }
            )
    return series


def _build_group_metric_summary(returns: list[float]) -> dict:
    metrics = _build_return_metrics(returns)
    return {
        "cumulative_return": metrics["cumulative_return"],
        "win_rate": metrics["win_rate"],
        "sharpe": metrics["sharpe"],
    }


def _build_group_stability(daily_items: list[dict]) -> dict:
    grouped: dict[tuple[str, str], dict] = {}

    for daily_item in daily_items:
        as_of = daily_item["as_of"]
        for version_key in ("v1", "v1_1"):
            top_candidate = _extract_top1_candidate(daily_item[version_key])
            top1_next_day_return = _extract_top1_next_day_return(daily_item[version_key])
            if top_candidate is None or top1_next_day_return is None:
                continue

            industry = str(top_candidate.get("industry") or "UNKNOWN")
            market_cap_bucket = str(top_candidate.get("market_cap_bucket") or "UNKNOWN")
            group = grouped.setdefault(
                (industry, market_cap_bucket),
                {"sample_days": set(), "v1": [], "v1_1": []},
            )
            group["sample_days"].add(as_of)
            group[version_key].append(top1_next_day_return)

    items = []
    for (industry, market_cap_bucket), group in grouped.items():
        sample_days = len(group["sample_days"])
        v1_metrics = _build_group_metric_summary(group["v1"])
        v1_1_metrics = _build_group_metric_summary(group["v1_1"])
        diff = {
            "excess_cumulative_return": _round_metric(
                v1_1_metrics["cumulative_return"] - v1_metrics["cumulative_return"]
            ),
            "excess_sharpe": _round_metric(v1_1_metrics["sharpe"] - v1_metrics["sharpe"]),
        }
        items.append(
            {
                "industry": industry,
                "market_cap_bucket": market_cap_bucket,
                "sample_days": sample_days,
                "v1": v1_metrics,
                "v1_1": v1_1_metrics,
                "diff": diff,
                "stability_flag": "LOW_SAMPLE" if sample_days < _LOW_SAMPLE_DAYS else "OK",
            }
        )

    items.sort(
        key=lambda item: (
            -item["sample_days"],
            -item["diff"]["excess_cumulative_return"],
            item["industry"],
            item["market_cap_bucket"],
        )
    )

    return {"group_key": _GROUP_STABILITY_KEY, "items": items}


def _build_analytics(daily_items: list[dict]) -> dict:
    daily_return_series = _build_daily_return_series(daily_items)
    v1_metrics = _build_return_metrics([item["top1_next_day_return"] for item in daily_return_series["v1"]])
    v1_1_metrics = _build_return_metrics([item["top1_next_day_return"] for item in daily_return_series["v1_1"]])
    return_metrics = {
        "v1": v1_metrics,
        "v1_1": v1_1_metrics,
        "diff": {
            "excess_cumulative_return_v1_1_vs_v1": _round_metric(
                v1_1_metrics["cumulative_return"] - v1_metrics["cumulative_return"]
            ),
            "excess_sharpe_v1_1_vs_v1": _round_metric(v1_1_metrics["sharpe"] - v1_metrics["sharpe"]),
        },
    }
    return {
        "return_metrics": return_metrics,
        "daily_return_series": daily_return_series,
        "group_stability": _build_group_stability(daily_items),
    }


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
    analytics = _build_analytics(daily_items)

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
            "analytics": analytics,
        },
        warnings=[],
    ) | {"errors": errors}
