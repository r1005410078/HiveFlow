from __future__ import annotations

from hiveflow.domain.aggregates.position_book import PositionBook, PositionInput
from hiveflow.domain.positions import Position


class FakePositionRepository:
    def __init__(self) -> None:
        self.items: list[Position] = []

    def list(self) -> list[Position]:
        return list(self.items)

    def add(self, position: Position) -> None:
        self.items.append(position)

    def add_many(self, positions: list[Position]) -> None:
        self.items.extend(positions)

    def replace_all(self, positions: list[Position]) -> None:
        self.items = list(positions)


def test_position_book_append_mode_keeps_existing_items() -> None:
    # 验证 append 模式会保留旧数据并追加新持仓。
    repo = FakePositionRepository()
    repo.add(Position(symbol="BTC", quantity=1, market_value=100000, weight=0.5))
    aggregate = PositionBook(repository=repo)

    imported = aggregate.apply_import(
        rows=[PositionInput(symbol="ETH", quantity=2, market_value=20000, weight=0.2)],
        mode="append",
    )
    assert imported == 1
    assert len(repo.list()) == 2


def test_position_book_replace_mode_overwrites_all_items() -> None:
    # 验证 replace 模式会覆盖旧持仓。
    repo = FakePositionRepository()
    repo.add(Position(symbol="BTC", quantity=1, market_value=100000, weight=0.5))
    aggregate = PositionBook(repository=repo)

    imported = aggregate.apply_import(
        rows=[PositionInput(symbol="ETH", quantity=2, market_value=20000, weight=0.2)],
        mode="replace",
    )
    assert imported == 1
    assert len(repo.list()) == 1
    assert repo.list()[0].symbol == "ETH"
