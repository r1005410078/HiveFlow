from uuid import uuid4

from application.contracts.cli_output import ok_output


def run_daily(as_of: str, root) -> dict:
    # root 预留给后续持久化与工作目录上下文使用。
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    return ok_output(
        command="hf pipeline daily",
        run_id=run_id,
        data={
            "as_of": as_of,
            "data_manifest_id": f"dm_{as_of.replace('-', '')}_{str(uuid4())[:6]}",
            "execution_plan": {"orders": []},
        },
    )
