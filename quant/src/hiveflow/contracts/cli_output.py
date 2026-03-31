from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok_output(command: str, run_id: str, data: dict, warnings: list | None = None) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": command,
        "run_id": run_id,
        "status": "ok",
        "generated_at": _now_iso(),
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": data,
        "warnings": warnings or [],
        "errors": [],
    }
