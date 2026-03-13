"""当前策略应用服务。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.decision_logs import UserPreference
from hiveflow.domain.strategies import Strategy

_CURRENT_STRATEGY_KEY = "current_strategy"


@dataclass(frozen=True)
class CurrentStrategyResult:
    """当前策略读取/设置结果。"""

    # 当前策略名。
    current_strategy: str | None

    def to_dict(self) -> dict[str, str | None]:
        """转换为字典，便于 JSON 输出。"""
        return {"current_strategy": self.current_strategy}


def show_current_strategy() -> CurrentStrategyResult:
    """读取当前策略。"""
    create_all_tables()
    with get_session() as session:
        pref = session.exec(
            select(UserPreference).where(UserPreference.key == _CURRENT_STRATEGY_KEY)
        ).first()
    return CurrentStrategyResult(current_strategy=(pref.value if pref else None))


def set_current_strategy(name: str) -> CurrentStrategyResult:
    """设置当前策略。"""
    create_all_tables()
    with get_session() as session:
        strategy = session.exec(select(Strategy).where(Strategy.name == name)).first()
        if strategy is None:
            raise ValueError("策略不存在，无法设置为当前策略。")

        pref = session.exec(
            select(UserPreference).where(UserPreference.key == _CURRENT_STRATEGY_KEY)
        ).first()
        if pref is None:
            session.add(UserPreference(key=_CURRENT_STRATEGY_KEY, value=name))
        else:
            pref.value = name
            session.add(pref)
        session.commit()

    return CurrentStrategyResult(current_strategy=name)
