"""领域层公共工具。"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """返回当前 UTC 时间，用于默认时间戳。"""
    return datetime.now(timezone.utc)

