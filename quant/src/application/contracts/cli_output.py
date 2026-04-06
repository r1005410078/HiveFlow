from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def error_output(command: str, run_id: str, errors: list[dict]) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": command,
        "run_id": run_id,
        "status": "error",
        "generated_at": _now_iso(),
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": {},
        "warnings": [],
        "errors": errors,
    }


def ok_output(command: str, run_id: str, data: dict, warnings: list[dict] | None = None) -> dict:
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
