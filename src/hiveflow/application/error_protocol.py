"""全局错误码与错误对象协议。"""

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from hiveflow.domain.common import utc_now


class ErrorCode(str, Enum):
    """全局统一错误码。"""

    DATA_SOURCE_EMPTY = "E_DATA_SOURCE_EMPTY"
    DATA_INSUFFICIENT_SAMPLES = "E_DATA_INSUFFICIENT_SAMPLES"
    SIGNAL_REQUIRED_MISSING = "E_SIGNAL_REQUIRED_MISSING"
    STYLE_EVAL_FAILED = "E_STYLE_EVAL_FAILED"
    PARAM_INVALID = "E_PARAM_INVALID"
    CONFIG_INVALID = "E_CONFIG_INVALID"
    DEPENDENCY_UNAVAILABLE = "E_DEPENDENCY_UNAVAILABLE"
    PIPELINE_ABORTED_STRICT = "E_PIPELINE_ABORTED_STRICT"
    STORAGE_WRITE_FAILED = "E_STORAGE_WRITE_FAILED"
    INTERNAL_UNEXPECTED = "E_INTERNAL_UNEXPECTED"


def new_trace_id() -> str:
    """生成本次运行 trace_id。"""
    return uuid4().hex


def build_error_payload(
    code: ErrorCode,
    message: str,
    context: str,
    details: dict | None = None,
    hint: dict | str | None = None,
    trace_id: str | None = None,
) -> dict:
    """构建统一错误对象。"""
    return {
        "code": code.value,
        "message": message,
        "context": context,
        "as_of": utc_now().isoformat(),
        "details": details or {},
        "trace_id": trace_id or new_trace_id(),
        "hint": hint if hint is not None else {},
    }
