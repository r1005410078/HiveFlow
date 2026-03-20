"""风格回测结果存档模型。"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class StyleBacktestResult(SQLModel, table=True):
    """style backtest-rank 持久化记录。"""

    id: int | None = Field(default=None, primary_key=True)
    run_id: str
    as_of: datetime
    feature_set_version: str | None = None
    style_preset_version: str | None = None
    symbols_hash: str | None = None
    params_hash: str | None = None
    code_version: str | None = None
    objective: str | None = None
    constraints_json: str | None = None
    search_method: str | None = None
    candidates_count: int | None = None
    valid_candidates_count: int | None = None
    best_candidate_json: str | None = None
    sort_key: str
    tie_breaker: str
    styles_json: str
    rank_table_json: str
    backtest_window_start: datetime | None = None
    backtest_window_end: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
