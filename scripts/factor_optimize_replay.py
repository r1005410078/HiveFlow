#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib import request


DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT_DIR = "docs/analysis/factor_optimization/replay"
ENDPOINT_PATH = "/api/v1/factor-optimization/evaluate"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Replay factor optimize evaluations across a date range and generate JSON/Markdown reports.",
    )
    parser.add_argument("--server-url", default=DEFAULT_SERVER_URL)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--factors", required=True, help="Comma-separated factor names")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


def date_range(start_date: str, end_date: str) -> list[str]:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    if start > end:
        raise ValueError("start-date must be on or before end-date")

    days: list[str] = []
    current = start
    while current <= end:
        days.append(current.isoformat())
        current += timedelta(days=1)
    return days


def build_request_payload(as_of: str, factors: list[str]) -> dict[str, Any]:
    return {
        "start_date": as_of,
        "end_date": as_of,
        "factor_names": factors,
        "constraints": {},
    }


def post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def extract_daily_metrics(as_of: str, response: dict[str, Any]) -> dict[str, Any]:
    data = response.get("data", {}) if isinstance(response, dict) else {}
    release_gate = data.get("release_gate", {}) if isinstance(data, dict) else {}
    correlation_analysis = data.get("correlation_analysis", {}) if isinstance(data, dict) else {}
    top_combinations = data.get("top_combinations", {}) if isinstance(data, dict) else {}
    top_items = top_combinations.get("items", []) if isinstance(top_combinations, dict) else []
    top1_factors = []
    if top_items and isinstance(top_items[0], dict):
        top1_factors = top_items[0].get("factors", []) or []

    return {
        "as_of": as_of,
        "fetch_status": "ok",
        "release_gate_status": release_gate.get("status", "fail") if isinstance(release_gate, dict) else "fail",
        "alert_count": correlation_analysis.get("alert_count", 0) if isinstance(correlation_analysis, dict) else 0,
        "top1_factors": top1_factors,
    }


def fetch_day(server_url: str, as_of: str, factors: list[str]) -> dict[str, Any]:
    url = server_url.rstrip("/") + ENDPOINT_PATH
    payload = build_request_payload(as_of, factors)
    try:
        response = post_json(url, payload)
        if not isinstance(response, dict):
            raise ValueError("response is not a JSON object")
        daily = extract_daily_metrics(as_of, response)
        return daily
    except Exception as exc:  # noqa: BLE001 - replay should continue across days.
        return {
            "as_of": as_of,
            "fetch_status": "error",
            "release_gate_status": "unknown",
            "alert_count": 0,
            "top1_factors": [],
            "error_message": str(exc),
        }


def summarize(daily_items: list[dict[str, Any]]) -> dict[str, Any]:
    days = len(daily_items)
    ok_items = [item for item in daily_items if item.get("fetch_status") == "ok"]
    error_days = days - len(ok_items)
    pass_days = sum(1 for item in ok_items if item.get("release_gate_status") == "pass")
    watch_days = sum(1 for item in ok_items if item.get("release_gate_status") == "watch")
    fail_days = sum(1 for item in ok_items if item.get("release_gate_status") == "fail")
    alert_sum = sum(int(item.get("alert_count", 0) or 0) for item in ok_items)
    avg_alert_count = round(alert_sum / len(ok_items), 6) if ok_items else 0.0

    top1_change_days = 0
    previous_top1: list[str] | None = None
    for item in ok_items:
        current_top1 = list(item.get("top1_factors", []) or [])
        if previous_top1 is not None and current_top1 != previous_top1:
            top1_change_days += 1
        previous_top1 = current_top1

    return {
        "days": days,
        "error_days": error_days,
        "pass_days": pass_days,
        "watch_days": watch_days,
        "fail_days": fail_days,
        "avg_alert_count": avg_alert_count,
        "top1_change_days": top1_change_days,
    }


def render_markdown(start_date: str, end_date: str, summary: dict[str, Any], daily_items: list[dict[str, Any]]) -> str:
    error_dates = [item["as_of"] for item in daily_items if item.get("fetch_status") == "error"]
    fail_dates = [item["as_of"] for item in daily_items if item.get("release_gate_status") == "fail"]
    watch_dates = [item["as_of"] for item in daily_items if item.get("release_gate_status") == "watch"]

    lines: list[str] = []
    lines.append(f"# Factor Optimize Replay Report ({start_date} to {end_date})")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- days: {summary['days']}")
    lines.append(f"- error_days: {summary['error_days']}")
    lines.append(f"- pass_days: {summary['pass_days']}")
    lines.append(f"- watch_days: {summary['watch_days']}")
    lines.append(f"- fail_days: {summary['fail_days']}")
    lines.append(f"- avg_alert_count: {summary['avg_alert_count']}")
    lines.append(f"- top1_change_days: {summary['top1_change_days']}")
    lines.append("")
    lines.append("## Fetch Errors")
    lines.append("")
    lines.append(f"- error_dates: {', '.join(error_dates) if error_dates else 'none'}")
    lines.append("")
    lines.append("## Watch / Fail Dates")
    lines.append("")
    lines.append(f"- watch_dates: {', '.join(watch_dates) if watch_dates else 'none'}")
    lines.append(f"- fail_dates: {', '.join(fail_dates) if fail_dates else 'none'}")
    lines.append("")
    lines.append("## Top1 Changes")
    lines.append("")
    lines.append(f"- top1_change_days: {summary['top1_change_days']}")
    lines.append("")
    lines.append("## Daily Items")
    lines.append("")
    for item in daily_items:
        error_suffix = f", error_message={item.get('error_message')}" if item.get("fetch_status") == "error" else ""
        lines.append(
            f"- {item['as_of']}: fetch_status={item.get('fetch_status')}, status={item.get('release_gate_status')}, alert_count={item.get('alert_count', 0)}, top1_factors={item.get('top1_factors', [])}{error_suffix}"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    factors = [factor.strip() for factor in args.factors.split(",") if factor.strip()]
    if not factors:
        raise SystemExit("--factors must contain at least one factor name")

    days = date_range(args.start_date, args.end_date)
    daily_items = [fetch_day(args.server_url, as_of, factors) for as_of in days]
    summary = summarize(daily_items)

    repo_root = Path(__file__).resolve().parents[1]
    output_dir = (repo_root / Path(args.output_dir)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"replay_{args.start_date}_{args.end_date}"
    json_path = output_dir / f"{stem}.json"
    md_path = output_dir / f"{stem}.md"

    report = {
        "summary": summary,
        "daily_items": daily_items,
    }

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(args.start_date, args.end_date, summary, daily_items), encoding="utf-8")

    print(json_path)
    print(md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
