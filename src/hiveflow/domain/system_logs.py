"""系统级运行日志模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class SystemLog(SQLModel, table=True):
    """系统执行日志（用于严格模式失败追踪）。"""

    id: int | None = Field(default=None, primary_key=True)
    trace_id: str
    error_code: str
    context: str
    message: str
    details_json: str | None = None
    hint_json: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
