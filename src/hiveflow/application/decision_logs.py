"""决策日志应用服务。"""

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.decision_logs import DecisionLog


def record_decision_log(summary: str, decision_type: str, notes: str | None) -> None:
    """记录一条决策日志。"""
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

