"""决策日志与用户偏好模型。"""

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class DecisionLog(SQLModel, table=True):
    """用户决策记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 决策摘要。
    summary: str
    # 决策类型，如 rebalance / risk-control。
    decision_type: str
    # 补充说明。
    notes: str | None = None
    # 创建时间（UTC）。
    created_at: datetime = Field(default_factory=utc_now)


class UserPreference(SQLModel, table=True):
    """用户偏好键值记录。"""

    # 记录主键。
    id: int | None = Field(default=None, primary_key=True)
    # 偏好键名。
    key: str
    # 偏好值（字符串化存储）。
    value: str
    # 最近更新时间（UTC）。
    updated_at: datetime = Field(default_factory=utc_now)
