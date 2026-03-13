"""决策日志应用服务。"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.decision_logs import DecisionLog


@dataclass(frozen=True)
class DecisionLogView:
    """决策日志只读视图。"""

    # 日志主键。
    id: int
    # 决策摘要。
    summary: str
    # 决策类型。
    decision_type: str
    # 决策备注。
    notes: str | None
    # 创建时间（UTC ISO 格式字符串）。
    created_at: str

    def to_dict(self) -> dict[str, int | str | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "id": self.id,
            "summary": self.summary,
            "decision_type": self.decision_type,
            "notes": self.notes,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class DecisionLogExportResult:
    """决策日志导出结果。"""

    # 导出文件路径。
    file: str
    # 导出总条数。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        """转换为字典，便于 JSON 输出。"""
        return {"file": self.file, "rows": self.rows}


def record_decision_log(summary: str, decision_type: str, notes: str | None) -> None:
    """记录一条决策日志。

    Args:
        summary: 决策摘要。
        decision_type: 决策类型。
        notes: 决策备注。
    """
    create_all_tables()
    with get_session() as session:
        session.add(
            DecisionLog(
                summary=summary,
                decision_type=decision_type,
                notes=notes,
            )
        )
        session.commit()


def list_decision_logs(limit: int = 100) -> list[DecisionLogView]:
    """按时间倒序读取决策日志。

    Args:
        limit: 最多返回的日志条数，默认 100 条。

    Returns:
        决策日志视图列表（按创建时间倒序）。
    """
    create_all_tables()
    with get_session() as session:
        logs = session.exec(select(DecisionLog).order_by(DecisionLog.created_at.desc())).all()

    return [
        DecisionLogView(
            id=log.id or 0,
            summary=log.summary,
            decision_type=log.decision_type,
            notes=log.notes,
            created_at=log.created_at.isoformat(),
        )
        for log in logs[: max(limit, 0)]
    ]


def export_decision_logs(file: Path, limit: int = 1000) -> DecisionLogExportResult:
    """导出决策日志为 CSV 文件。

    Args:
        file: 导出文件路径。
        limit: 最多导出的日志条数，默认 1000 条。

    Returns:
        导出结果（文件路径和条数）。
    """
    logs = list_decision_logs(limit=limit)
    file.parent.mkdir(parents=True, exist_ok=True)

    with file.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=["id", "summary", "decision_type", "notes", "created_at"],
        )
        writer.writeheader()
        for item in logs:
            writer.writerow(item.to_dict())

    return DecisionLogExportResult(file=str(file), rows=len(logs))
