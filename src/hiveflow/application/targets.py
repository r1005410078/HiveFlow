"""目标持仓应用服务。"""

import json
from csv import DictReader
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.strategies import Strategy
from hiveflow.services.allocation_engine import generate_target_allocations


@dataclass(frozen=True)
class TargetAllocationView:
    # 策略名称。
    strategy_name: str
    # 策略类型。
    strategy_type: str | None
    # 策略维度。
    dimension: str | None
    # 标的代码。
    symbol: str
    # 目标权重（0~1）。
    target_weight: float

    def to_dict(self) -> dict[str, str | float]:
        return {
            "strategy_name": self.strategy_name,
            "strategy_type": self.strategy_type,
            "dimension": self.dimension,
            "symbol": self.symbol,
            "target_weight": round(self.target_weight, 6),
        }


@dataclass(frozen=True)
class TargetImportResult:
    # 实际导入条数。
    imported: int
    # 导入模式：append/replace。
    mode: str
    # 导入文件路径。
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "mode": self.mode, "file": self.file}


@dataclass(frozen=True)
class TargetTemplateResult:
    # 模板文件输出路径。
    file: str
    # 模板示例行数（不含表头）。
    rows: int

    def to_dict(self) -> dict[str, int | str]:
        return {"file": self.file, "rows": self.rows}


@dataclass(frozen=True)
class TargetGenerateResult:
    # 生成所使用的策略名称。
    strategy: str
    # 策略类型。
    strategy_type: str
    # 策略维度。
    dimension: str | None
    # 模板来源：dimension / type。
    template_source: str
    # 生成条数。
    generated: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "strategy": self.strategy,
            "strategy_type": self.strategy_type,
            "dimension": self.dimension,
            "template_source": self.template_source,
            # 兼容旧字段，后续可逐步移除。
            "category": self.strategy_type,
            "generated": self.generated,
        }


@dataclass(frozen=True)
class TargetTemplateConfigView:
    # 配置文件路径。
    file: str
    # 类型模板。
    type_presets: dict[str, dict[str, float]]
    # 维度模板。
    dimension_presets: dict[str, dict[str, float]]

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file,
            "type_presets": self.type_presets,
            "dimension_presets": self.dimension_presets,
        }


@dataclass(frozen=True)
class TargetTemplateSetResult:
    # 作用域：type/dimension。
    scope: str
    # 模板键名。
    key: str
    # 最新权重。
    weights: dict[str, float]
    # 配置文件路径。
    file: str

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope,
            "key": self.key,
            "weights": self.weights,
            "file": self.file,
        }


@dataclass(frozen=True)
class TargetTemplateRollbackResult:
    # 恢复到的版本号。
    restored_version: int
    # 配置文件路径。
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"restored_version": self.restored_version, "file": self.file}


def list_target_allocations(strategy_name: str | None = None) -> list[TargetAllocationView]:
    """读取并返回目标持仓（按策略名和标的排序）。

    Returns:
        list[TargetAllocationView]: 目标持仓视图列表。
    """
    create_all_tables()
    with get_session() as session:
        rows = session.exec(select(TargetAllocation)).all()
        strategies = session.exec(select(Strategy)).all()
    strategy_meta = {item.name: item for item in strategies}
    if strategy_name:
        rows = [row for row in rows if row.strategy_name == strategy_name]
    return [
        TargetAllocationView(
            strategy_name=row.strategy_name,
            strategy_type=(
                strategy_meta[row.strategy_name].category
                if row.strategy_name in strategy_meta
                else None
            ),
            dimension=(
                strategy_meta[row.strategy_name].dimension
                if row.strategy_name in strategy_meta
                else None
            ),
            symbol=row.symbol,
            target_weight=row.target_weight,
        )
        for row in sorted(rows, key=lambda item: (item.strategy_name, item.symbol))
    ]


def import_target_allocations_from_csv(file: Path, mode: str) -> TargetImportResult:
    """从 CSV 导入目标持仓。

    Args:
        file: CSV 文件路径。
        mode: 导入模式，仅支持 append 或 replace。

    Returns:
        TargetImportResult: 导入结果摘要。
    """
    if mode not in {"append", "replace"}:
        raise ValueError("导入模式仅支持 append 或 replace。")
    if not file.exists() or not file.is_file():
        raise FileNotFoundError("CSV 文件不存在或不可读取。")

    create_all_tables()
    imported = 0
    with get_session() as session:
        if mode == "replace":
            session.exec(delete(TargetAllocation))

        with file.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = DictReader(csv_file)
            required = {"strategy_name", "symbol", "target_weight"}
            if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
                raise ValueError("CSV 列必须包含：strategy_name, symbol, target_weight")

            for row in reader:
                strategy_name = (row.get("strategy_name") or "").strip()
                symbol = (row.get("symbol") or "").strip().upper()
                if not strategy_name or not symbol:
                    continue
                session.exec(
                    delete(TargetAllocation).where(
                        (TargetAllocation.strategy_name == strategy_name)
                        & (TargetAllocation.symbol == symbol)
                    )
                )
                session.add(
                    TargetAllocation(
                        strategy_name=strategy_name,
                        symbol=symbol,
                        target_weight=float(row.get("target_weight") or 0.0),
                    )
                )
                imported += 1
        session.commit()

    return TargetImportResult(imported=imported, mode=mode, file=str(file))


def export_target_template(file: Path) -> TargetTemplateResult:
    """导出目标持仓 CSV 模板。

    Args:
        file: 模板输出路径。

    Returns:
        TargetTemplateResult: 模板生成结果。
    """
    file.parent.mkdir(parents=True, exist_ok=True)
    template = (
        "strategy_name,symbol,target_weight\n"
        "进攻型默认策略,BTC,0.50\n"
        "进攻型默认策略,ETH,0.30\n"
        "进攻型默认策略,USDT,0.20\n"
    )
    file.write_text(template, encoding="utf-8")
    return TargetTemplateResult(file=str(file), rows=3)


_TYPE_PRESETS: dict[str, dict[str, float]] = {
    "进攻型": {"BTC": 0.50, "ETH": 0.30, "USDT": 0.20},
    "防守型": {"BTC": 0.20, "ETH": 0.20, "USDT": 0.60},
    "长期型": {"BTC": 0.40, "ETH": 0.40, "USDT": 0.20},
}

_DIMENSION_PRESETS: dict[str, dict[str, float]] = {
    "趋势|动量": {"BTC": 0.45, "ETH": 0.45, "USDT": 0.10},
    "波动|防守": {"BTC": 0.15, "ETH": 0.15, "USDT": 0.70},
}


def _template_config_file() -> Path:
    """返回目标模板配置文件路径。"""
    return Path(Settings().target_template_file)


def _template_history_file() -> Path:
    """返回模板历史快照文件路径。"""
    return _template_config_file().with_name("target-templates.history.json")


def _load_template_presets_from_config() -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """从外部配置读取模板；读取失败时回退到内置模板。"""
    config_file = _template_config_file()
    if not config_file.exists() or not config_file.is_file():
        return _TYPE_PRESETS, _DIMENSION_PRESETS

    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _TYPE_PRESETS, _DIMENSION_PRESETS

    raw_type = payload.get("type_presets", {})
    raw_dimension = payload.get("dimension_presets", {})
    if not isinstance(raw_type, dict) or not isinstance(raw_dimension, dict):
        return _TYPE_PRESETS, _DIMENSION_PRESETS

    type_presets: dict[str, dict[str, float]] = dict(_TYPE_PRESETS)
    dimension_presets: dict[str, dict[str, float]] = dict(_DIMENSION_PRESETS)

    for key, value in raw_type.items():
        if isinstance(key, str) and isinstance(value, dict):
            try:
                type_presets[key] = {str(k).upper(): float(v) for k, v in value.items()}
            except (TypeError, ValueError):
                continue
    for key, value in raw_dimension.items():
        if isinstance(key, str) and isinstance(value, dict):
            try:
                dimension_presets[key] = {str(k).upper(): float(v) for k, v in value.items()}
            except (TypeError, ValueError):
                continue

    return type_presets, dimension_presets


def _read_raw_template_config() -> dict[str, object]:
    """读取原始模板配置，不存在时返回空结构。"""
    config_file = _template_config_file()
    if not config_file.exists() or not config_file.is_file():
        return {"type_presets": {}, "dimension_presets": {}}
    try:
        payload = json.loads(config_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"type_presets": {}, "dimension_presets": {}}
    if not isinstance(payload, dict):
        return {"type_presets": {}, "dimension_presets": {}}
    payload.setdefault("type_presets", {})
    payload.setdefault("dimension_presets", {})
    return payload


def _read_template_history() -> list[dict[str, object]]:
    """读取模板历史快照列表。"""
    history_file = _template_history_file()
    if not history_file.exists() or not history_file.is_file():
        return []
    try:
        payload = json.loads(history_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _append_template_snapshot(config_payload: dict[str, object], reason: str) -> None:
    """追加一条模板快照。"""
    history = _read_template_history()
    next_version = (history[-1].get("version", 0) if history else 0) + 1
    if not isinstance(next_version, int):
        next_version = len(history) + 1
    history.append(
        {
            "version": next_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "payload": config_payload,
        }
    )
    history_file = _template_history_file()
    history_file.parent.mkdir(parents=True, exist_ok=True)
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def get_target_template_config() -> TargetTemplateConfigView:
    """获取当前生效的模板配置（含默认模板）。"""
    type_presets, dimension_presets = _load_template_presets_from_config()
    return TargetTemplateConfigView(
        file=str(_template_config_file()),
        type_presets=type_presets,
        dimension_presets=dimension_presets,
    )


def set_target_template_preset(scope: str, key: str, weights: dict[str, float]) -> TargetTemplateSetResult:
    """写入单条模板配置。"""
    normalized_scope = scope.strip().lower()
    if normalized_scope not in {"type", "dimension"}:
        raise ValueError("scope 仅支持 type 或 dimension。")
    normalized_key = key.strip()
    if not normalized_key:
        raise ValueError("key 不能为空。")
    if not weights:
        raise ValueError("weights 不能为空。")

    normalized_weights = {symbol.strip().upper(): float(value) for symbol, value in weights.items()}
    payload = _read_raw_template_config()
    _append_template_snapshot(config_payload=payload, reason=f"set:{normalized_scope}/{normalized_key}")
    bucket_name = "type_presets" if normalized_scope == "type" else "dimension_presets"
    bucket = payload.get(bucket_name)
    if not isinstance(bucket, dict):
        bucket = {}
    bucket[normalized_key] = normalized_weights
    payload[bucket_name] = bucket

    config_file = _template_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return TargetTemplateSetResult(
        scope=normalized_scope,
        key=normalized_key,
        weights=normalized_weights,
        file=str(config_file),
    )


def rollback_target_template(version: int | None = None) -> TargetTemplateRollbackResult:
    """将模板配置回滚到历史版本。

    Args:
        version: 目标版本号；不传时回滚到最近一次快照。

    Returns:
        TargetTemplateRollbackResult: 回滚结果。
    """
    history = _read_template_history()
    if not history:
        raise ValueError("没有可用的模板历史快照。")

    selected: dict[str, object] | None = None
    if version is None:
        selected = history[-1]
    else:
        for item in history:
            if item.get("version") == version:
                selected = item
                break
    if selected is None:
        raise ValueError("指定版本不存在。")

    payload = selected.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("历史快照损坏，无法回滚。")

    config_file = _template_config_file()
    config_file.parent.mkdir(parents=True, exist_ok=True)
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    restored_version = selected.get("version")
    if not isinstance(restored_version, int):
        restored_version = 0
    return TargetTemplateRollbackResult(restored_version=restored_version, file=str(config_file))


def _normalize_dimension(value: str | None) -> str:
    """将维度字符串规范化，避免顺序和空格影响匹配。"""
    if not value:
        return ""
    parts = sorted({item.strip() for item in value.split("|") if item.strip()})
    return "|".join(parts)


def _select_template_allocations(strategy_type: str, dimension: str | None) -> tuple[dict[str, float], str]:
    """根据策略类型与维度选择目标持仓模板。"""
    type_presets, dimension_presets_raw = _load_template_presets_from_config()
    normalized_dimension = _normalize_dimension(dimension)
    dimension_templates = {
        _normalize_dimension(key): value for key, value in dimension_presets_raw.items()
    }
    if normalized_dimension and normalized_dimension in dimension_templates:
        return dimension_templates[normalized_dimension], "dimension"

    normalized_type = strategy_type.strip()
    if normalized_type in type_presets:
        return type_presets[normalized_type], "type"

    return {"BTC": 0.34, "ETH": 0.33, "USDT": 0.33}, "type"


def _default_allocations_for_category(category: str) -> dict[str, float]:
    """按策略类型返回默认目标权重配置。"""
    normalized = category.strip()
    if normalized in _TYPE_PRESETS:
        return _TYPE_PRESETS[normalized]
    return {"BTC": 0.34, "ETH": 0.33, "USDT": 0.33}


def generate_targets_for_strategy(strategy_name: str) -> TargetGenerateResult:
    """根据策略自动生成目标持仓（覆盖该策略已有目标）。"""
    create_all_tables()
    with get_session() as session:
        strategy = session.exec(select(Strategy).where(Strategy.name == strategy_name)).first()
        if strategy is None:
            raise ValueError("策略不存在，无法生成目标持仓。")

        session.exec(
            delete(TargetAllocation).where(TargetAllocation.strategy_name == strategy_name)
        )
        allocations, template_source = _select_template_allocations(
            strategy_type=strategy.category,
            dimension=strategy.dimension,
        )
        targets = generate_target_allocations(strategy_name=strategy_name, allocations=allocations)
        for item in targets:
            session.add(item)
        session.commit()

        return TargetGenerateResult(
            strategy=strategy_name,
            strategy_type=strategy.category,
            dimension=strategy.dimension,
            template_source=template_source,
            generated=len(targets),
        )
