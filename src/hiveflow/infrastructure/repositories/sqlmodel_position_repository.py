from __future__ import annotations

"""基于 SQLModel 的持仓仓储实现。"""

from sqlmodel import delete, select

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position
from hiveflow.domain.repositories import PositionRepository


class SQLModelPositionRepository(PositionRepository):
    """持仓仓储的 SQLModel 实现。"""

    def list(self) -> list[Position]:
        create_all_tables()
        with get_session() as session:
            return session.exec(select(Position)).all()

    def add(self, position: Position) -> None:
        create_all_tables()
        with get_session() as session:
            session.add(position)
            session.commit()

    def add_many(self, positions: list[Position]) -> None:
        create_all_tables()
        with get_session() as session:
            session.add_all(positions)
            session.commit()

    def replace_all(self, positions: list[Position]) -> None:
        create_all_tables()
        with get_session() as session:
            session.exec(delete(Position))
            session.add_all(positions)
            session.commit()
