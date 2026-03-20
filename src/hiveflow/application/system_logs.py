"""系统日志应用服务。"""

from __future__ import annotations

import json

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.system_logs import SystemLog


def record_system_log(
    *,
    trace_id: str,
    error_code: str,
    context: str,
    message: str,
    details: dict | None = None,
    hint: dict | str | None = None,
) -> None:
    """记录一条系统日志。"""
    create_all_tables()
    with get_session() as session:
        session.add(
            SystemLog(
                trace_id=trace_id,
                error_code=error_code,
                context=context,
                message=message,
                details_json=json.dumps(details or {}, ensure_ascii=False),
                hint_json=json.dumps(hint if hint is not None else {}, ensure_ascii=False),
            )
        )
        session.commit()
