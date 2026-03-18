# src/hiveflow/application/blend.py
"""多策略混合应用服务。"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.blend_configs import BlendConfig
from hiveflow.domain.common import utc_now
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.strategy_runs import StrategyRun


@dataclass(frozen=True)
class BlendConfigView:
    """BlendConfig 视图。"""
    id: int | None
    name: str
    strategy_names: list[str]
    weights: dict
    auto_optimized: bool
    optimize_metric: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "strategy_names": self.strategy_names,
            "weights": self.weights,
            "auto_optimized": self.auto_optimized,
            "optimize_metric": self.optimize_metric,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class BlendRunResult:
    """blend run 结果。"""
    name: str
    blend_weights: dict        # 各策略的混合权重
    asset_weights: dict        # 混合后的资产权重
    applied: bool

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "blend_weights": self.blend_weights,
            "asset_weights": self.asset_weights,
            "applied": self.applied,
        }


def create_blend(
    name: str,
    strategy_names: list[str],
    weights: list[float] | None,
    optimize_metric: str = "sharpe",
    settings: Settings | None = None,
) -> BlendConfigView:
    """创建 BlendConfig。weights=None 表示自动优化模式。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 手动权重归一化校验
    if weights is not None:
        total = sum(weights)
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"权重之和必须等于 1.0（当前：{total:.4f}）。"
            )
        weights_dict = dict(zip(strategy_names, weights))
    else:
        weights_dict = {}

    # 重名保护（Application 层）
    with get_session(app_settings) as session:
        existing = session.exec(
            select(BlendConfig).where(BlendConfig.name == name)
        ).first()
        if existing is not None:
            raise ValueError(f"Blend 配置 '{name}' 已存在，请使用不同名称。")

        record = BlendConfig(
            name=name,
            strategy_names=json.dumps(strategy_names),
            weights=json.dumps(weights_dict),
            auto_optimized=(weights is None),
            optimize_metric=optimize_metric,
        )
        session.add(record)
        session.commit()
        session.refresh(record)

    return _to_view(record)


def list_blends(settings: Settings | None = None) -> list[BlendConfigView]:
    """列出所有 BlendConfig。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        rows = session.exec(
            select(BlendConfig).order_by(BlendConfig.created_at.desc())
        ).all()

    return [_to_view(r) for r in rows]


def get_blend(name: str, settings: Settings | None = None) -> BlendConfigView:
    """按名称查询 BlendConfig，不存在则抛 ValueError。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        row = session.exec(
            select(BlendConfig).where(BlendConfig.name == name)
        ).first()

    if row is None:
        raise ValueError(f"Blend 配置 '{name}' 不存在。")
    return _to_view(row)


def _compute_auto_weights(
    strategy_names: list[str],
    metric: str,
    settings: Settings,
) -> dict:
    """从各策略最新 BacktestResult 的指标归一化计算 blend 权重。
    所有策略无 BacktestResult 或指标均为 0 时退回等权。
    """
    scores: dict[str, float] = {}

    with get_session(settings) as session:
        for name in strategy_names:
            row = session.exec(
                select(BacktestResult)
                .where(BacktestResult.strategy_name == name)
                .order_by(BacktestResult.created_at.desc())
            ).first()
            if row is None:
                scores[name] = 0.0
            elif metric == "sharpe":
                scores[name] = max(row.sharpe, 0.0)
            elif metric == "calmar":
                calmar = (
                    row.total_return / abs(row.max_drawdown)
                    if row.max_drawdown != 0.0
                    else 0.0
                )
                scores[name] = max(calmar, 0.0)
            else:  # "return"
                scores[name] = max(row.total_return, 0.0)

    total = sum(scores.values())
    if total == 0.0:
        n = len(strategy_names)
        return {name: 1.0 / n for name in strategy_names}
    return {name: v / total for name, v in scores.items()}


def run_blend(
    name: str,
    apply: bool = False,
    settings: Settings | None = None,
) -> BlendRunResult:
    """执行 blend：计算混合权重 + 资产权重，可选写入 TargetAllocation。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 1. 加载配置
    with get_session(app_settings) as session:
        config = session.exec(
            select(BlendConfig).where(BlendConfig.name == name)
        ).first()
    if config is None:
        raise ValueError(f"Blend 配置 '{name}' 不存在。")

    strategy_names: list[str] = json.loads(config.strategy_names)

    # 2. 计算 blend 权重
    if config.auto_optimized:
        blend_weights = _compute_auto_weights(
            strategy_names, config.optimize_metric, app_settings
        )
    else:
        blend_weights = json.loads(config.weights)

    # 3. 加权混合各策略的资产权重
    asset_weights: dict[str, float] = {}
    with get_session(app_settings) as session:
        for strategy_name, bw in blend_weights.items():
            run = session.exec(
                select(StrategyRun)
                .where(StrategyRun.strategy_name == strategy_name)
                .order_by(StrategyRun.run_at.desc())
            ).first()
            if run is None:
                raise ValueError(
                    f"策略 '{strategy_name}' 没有运行记录，请先执行 `hiveflow quant run`。"
                )
            for asset, w in json.loads(run.weights).items():
                asset_weights[asset] = asset_weights.get(asset, 0.0) + bw * float(w)

    # 归一化资产权重
    total_w = sum(asset_weights.values())
    if total_w > 0:
        asset_weights = {k: v / total_w for k, v in asset_weights.items()}

    # 4. 更新 BlendConfig.updated_at + 写入已计算的 blend_weights
    with get_session(app_settings) as session:
        row = session.exec(
            select(BlendConfig).where(BlendConfig.name == name)
        ).first()
        if row:
            row.weights = json.dumps(blend_weights)
            row.updated_at = utc_now()
            session.commit()

    # 5. 可选写入 TargetAllocation
    applied = False
    if apply:
        _apply_blend_weights(name, asset_weights, app_settings)
        applied = True

    return BlendRunResult(
        name=name,
        blend_weights=blend_weights,
        asset_weights=asset_weights,
        applied=applied,
    )


def _apply_blend_weights(
    blend_name: str,
    asset_weights: dict,
    settings: Settings,
) -> None:
    """写入 TargetAllocation，strategy_name = 'blend:<name>'。"""
    strategy_label = f"blend:{blend_name}"
    with get_session(settings) as session:
        session.exec(
            delete(TargetAllocation).where(
                TargetAllocation.strategy_name == strategy_label
            )
        )
        for symbol, weight in asset_weights.items():
            session.add(TargetAllocation(
                symbol=symbol,
                target_weight=weight,
                strategy_name=strategy_label,
            ))
        session.add(DecisionLog(
            decision_type="blend-apply",
            summary=f"blend run --apply: {blend_name} → {json.dumps(asset_weights)}",
        ))
        session.commit()


def _to_view(record: BlendConfig) -> BlendConfigView:
    return BlendConfigView(
        id=record.id,
        name=record.name,
        strategy_names=json.loads(record.strategy_names),
        weights=json.loads(record.weights),
        auto_optimized=record.auto_optimized,
        optimize_metric=record.optimize_metric,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )
