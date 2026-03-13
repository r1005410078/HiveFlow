from __future__ import annotations

"""持仓仓储接口定义。"""

from typing import Protocol

from hiveflow.domain.positions import Position


class PositionRepository(Protocol):
    """持仓仓储接口。"""

    def list(self) -> list[Position]:
        """返回全部持仓记录。"""

    def add(self, position: Position) -> None:
        """新增单条持仓记录。"""

    def add_many(self, positions: list[Position]) -> None:
        """批量新增持仓记录。"""

    def replace_all(self, positions: list[Position]) -> None:
        """原子替换全部持仓记录。"""

