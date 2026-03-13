from dataclasses import dataclass

from sqlmodel import Session, select

from hiveflow.db import create_all_tables, get_engine
from hiveflow.domain.slots import StrategySlot
from hiveflow.domain.strategies import Strategy


@dataclass(frozen=True)
class SlotSeed:
    name: str
    purpose: str
    allowed_category: str
    weight: float


def default_slots() -> list[SlotSeed]:
    """返回第一版默认策略席位定义。"""
    return [
        SlotSeed("进攻席位", "进攻资金", "进攻型", 0.4),
        SlotSeed("防守席位", "防守资金", "防守型", 0.3),
        SlotSeed("长期席位", "长期资金", "长期型", 0.3),
    ]


def default_strategy_categories() -> list[str]:
    """返回第一版默认策略分类。"""
    return ["进攻型", "防守型", "长期型"]


def _seed_slots(session: Session) -> None:
    """将默认席位写入数据库（已存在则跳过）。"""
    existing_names = set(session.exec(select(StrategySlot.name)).all())
    for slot in default_slots():
        if slot.name in existing_names:
            continue
        session.add(
            StrategySlot(
                name=slot.name,
                purpose=slot.purpose,
                allowed_category=slot.allowed_category,
                weight=slot.weight,
                enabled=True,
            )
        )


def _seed_strategy_categories(session: Session) -> None:
    """为每个默认分类写入一条基础策略（已存在则跳过）。"""
    existing_categories = set(session.exec(select(Strategy.category)).all())
    for category in default_strategy_categories():
        if category in existing_categories:
            continue
        session.add(
            Strategy(
                name=f"{category}默认策略",
                category=category,
                thesis=f"{category}基础策略",
            )
        )


def bootstrap_all() -> None:
    """初始化数据库并写入第一版基础种子数据。"""
    create_all_tables()
    engine = get_engine()
    with Session(engine) as session:
        _seed_slots(session)
        _seed_strategy_categories(session)
        session.commit()
