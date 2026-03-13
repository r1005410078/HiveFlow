from hiveflow.config import Settings
from hiveflow.domain.slots import StrategySlot
from hiveflow.services.bootstrap import default_slots, default_strategy_categories


def test_default_database_url_uses_sqlite() -> None:
    # 验证默认配置使用本地 SQLite 数据库。
    settings = Settings()
    assert settings.database_url.startswith("sqlite")


def test_strategy_slot_has_name_and_purpose() -> None:
    # 验证策略席位模型能正确保存名称和用途字段。
    slot = StrategySlot(name="进攻席位", purpose="进攻资金")
    assert slot.name == "进攻席位"
    assert slot.purpose == "进攻资金"


def test_default_slots_include_attack_defense_long_term() -> None:
    # 验证默认席位包含进攻、防守、长期三类。
    names = [slot.name for slot in default_slots()]
    assert names == ["进攻席位", "防守席位", "长期席位"]


def test_default_strategy_categories_match_slots() -> None:
    # 验证默认策略分类与席位体系一致（进攻/防守/长期）。
    categories = default_strategy_categories()
    assert set(categories) == {"进攻型", "防守型", "长期型"}
