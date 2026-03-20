"""风格回测结果存储应用服务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.common import utc_now
from hiveflow.domain.style_backtest_results import StyleBacktestResult


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass(frozen=True)
class StyleBacktestHistoryView:
    id: int
    run_id: str
    as_of: str
    sort_key: str
    styles_count: int
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "as_of": self.as_of,
            "sort_key": self.sort_key,
            "styles_count": self.styles_count,
            "created_at": self.created_at,
        }


def save_style_backtest_result(payload: dict, settings: Settings | None = None) -> StyleBacktestHistoryView:
    """落库一条 style backtest-rank 结果，并返回摘要视图。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    run_id = payload.get("run_id") or f"style-{utc_now().strftime('%Y%m%d%H%M%S%f')}"
    as_of = _parse_iso_datetime(payload.get("as_of")) or utc_now()
    backtest_window = payload.get("backtest_window", {}) or {}
    row = StyleBacktestResult(
        run_id=run_id,
        as_of=as_of,
        feature_set_version=payload.get("feature_set_version"),
        style_preset_version=payload.get("style_preset_version"),
        symbols_hash=payload.get("symbols_hash"),
        params_hash=payload.get("params_hash"),
        code_version=payload.get("code_version"),
        objective=payload.get("objective"),
        constraints_json=json.dumps(payload.get("constraints", {}), ensure_ascii=False),
        search_method=payload.get("search_method"),
        candidates_count=payload.get("candidates_count"),
        valid_candidates_count=payload.get("valid_candidates_count"),
        best_candidate_json=json.dumps(payload.get("best_candidate"), ensure_ascii=False),
        sort_key=payload.get("sort_key", "calmar"),
        tie_breaker=payload.get("tie_breaker", ""),
        styles_json=json.dumps(payload.get("styles", []), ensure_ascii=False),
        rank_table_json=json.dumps(payload.get("rank_table", []), ensure_ascii=False),
        backtest_window_start=_parse_iso_datetime(backtest_window.get("start")),
        backtest_window_end=_parse_iso_datetime(backtest_window.get("end")),
    )
    with get_session(app_settings) as session:
        session.add(row)
        session.commit()
        session.refresh(row)

    return StyleBacktestHistoryView(
        id=row.id or 0,
        run_id=row.run_id,
        as_of=row.as_of.isoformat(),
        sort_key=row.sort_key,
        styles_count=len(payload.get("styles", [])),
        created_at=row.created_at.isoformat(),
    )


def list_style_backtest_results(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[StyleBacktestHistoryView]:
    """按时间倒序列出风格回测结果。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)
    with get_session(app_settings) as session:
        rows = session.exec(
            select(StyleBacktestResult)
            .order_by(StyleBacktestResult.created_at.desc())
            .limit(limit)
        ).all()

    result: list[StyleBacktestHistoryView] = []
    for row in rows:
        styles = json.loads(row.styles_json)
        result.append(
            StyleBacktestHistoryView(
                id=row.id or 0,
                run_id=row.run_id,
                as_of=row.as_of.isoformat(),
                sort_key=row.sort_key,
                styles_count=len(styles),
                created_at=row.created_at.isoformat(),
            )
        )
    return result


def get_style_backtest_result(record_id: int, settings: Settings | None = None) -> dict:
    """按记录 ID 读取完整风格回测结果。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)
    with get_session(app_settings) as session:
        row = session.get(StyleBacktestResult, record_id)
        if row is None:
            raise ValueError(f"风格回测记录 #{record_id} 不存在。")

    return {
        "id": row.id,
        "run_id": row.run_id,
        "as_of": row.as_of.isoformat(),
        "feature_set_version": row.feature_set_version,
        "style_preset_version": row.style_preset_version,
        "symbols_hash": row.symbols_hash,
        "params_hash": row.params_hash,
        "code_version": row.code_version,
        "objective": row.objective,
        "constraints": json.loads(row.constraints_json) if row.constraints_json else {},
        "search_method": row.search_method,
        "candidates_count": row.candidates_count,
        "valid_candidates_count": row.valid_candidates_count,
        "sort_key": row.sort_key,
        "tie_breaker": row.tie_breaker,
        "styles": json.loads(row.styles_json),
        "rank_table": json.loads(row.rank_table_json),
        "best_candidate": json.loads(row.best_candidate_json) if row.best_candidate_json else None,
        "backtest_window": {
            "start": row.backtest_window_start.isoformat() if row.backtest_window_start else None,
            "end": row.backtest_window_end.isoformat() if row.backtest_window_end else None,
        },
        "created_at": row.created_at.isoformat(),
    }
