"""信号快照存档模型。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class SignalSnapshot(SQLModel, table=True):
    """signal snapshot 持久化记录。"""

    id: int | None = Field(default=None, primary_key=True)
    snapshot_id: str
    as_of: datetime
    symbol: str
    feature_set_version: str | None = None
    style_preset_version: str | None = None
    symbols_hash: str | None = None
    params_hash: str | None = None
    code_version: str | None = None
    signals_json: str
    category_metrics_json: str
    conflict_matrix_json: str
    data_window_start: datetime | None = None
    data_window_end: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
