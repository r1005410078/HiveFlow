"""策略席位应用服务。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.db import get_session
from hiveflow.domain.slots import StrategySlot
from hiveflow.services.bootstrap import bootstrap_all


@dataclass(frozen=True)
class SlotView:
    """席位只读视图。"""

    # 席位名称。
    name: str
    # 席位用途。
    purpose: str
    # 允许策略分类。
    allowed_category: str | None
    # 目标权重（0~1）。
    weight: float
    # 是否启用。
    enabled: bool

    def to_dict(self) -> dict[str, str | float | bool | None]:
        """转换为字典，便于 JSON 输出。"""
        return {
            "name": self.name,
            "purpose": self.purpose,
            "allowed_category": self.allowed_category,
            "weight": round(self.weight, 6),
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class SlotUpdateResult:
    """席位更新结果。"""

    # 席位名称。
    name: str
    # 最新权重。
    weight: float

    def to_dict(self) -> dict[str, str | float]:
        """转换为字典，便于 JSON 输出。"""
        return {"name": self.name, "weight": round(self.weight, 6)}


def list_slots() -> list[SlotView]:
    """列出策略席位。"""
    bootstrap_all()
    with get_session() as session:
        rows = session.exec(select(StrategySlot)).all()
    return [
        SlotView(
            name=row.name,
            purpose=row.purpose,
            allowed_category=row.allowed_category,
            weight=row.weight,
            enabled=row.enabled,
        )
        for row in sorted(rows, key=lambda item: item.name)
    ]


def set_slot_weight(name: str, weight: float) -> SlotUpdateResult:
    """更新席位权重。"""
    if weight < 0 or weight > 1:
        raise ValueError("weight 必须在 0 到 1 之间。")

    bootstrap_all()
    with get_session() as session:
        slot = session.exec(select(StrategySlot).where(StrategySlot.name == name)).first()
        if slot is None:
            raise ValueError("席位不存在，无法更新权重。")
        slot.weight = weight
        session.add(slot)
        session.commit()
        session.refresh(slot)
        return SlotUpdateResult(name=slot.name, weight=slot.weight)
