# M9 Portfolio Blend + 实盘绩效追踪 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现多策略加权混合（`quant blend`）和实盘绩效追踪（`perf`），形成"blend → execute → track → compare"完整链路。

**Architecture:** 遵循现有 Clean Architecture 四层结构，新增两个 SQLModel 实体（`BlendConfig`、`PortfolioSnapshot`）、两个 application 模块（`blend.py`、`perf.py`），并在 `cli.py` 中添加 `quant blend` 子命令组和 `perf` 命令组。

**Tech Stack:** Python + SQLModel + SQLite + Typer + Rich；无新增第三方依赖。

---

## 文件映射

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/hiveflow/domain/blend_configs.py` | BlendConfig SQLModel 实体 |
| 新建 | `src/hiveflow/domain/portfolio_snapshots.py` | PortfolioSnapshot SQLModel 实体 |
| 新建 | `src/hiveflow/application/blend.py` | blend CRUD + 权重计算 + apply |
| 新建 | `src/hiveflow/application/perf.py` | 快照落库 + compare 指标计算 |
| 新建 | `tests/test_blend.py` | blend 单元/集成测试 |
| 新建 | `tests/test_perf.py` | perf 单元/集成测试 |
| 新建 | `config/tracking.json` | cron 配置文件 |
| 修改 | `src/hiveflow/db.py` | 导入新实体触发建表 |
| 修改 | `src/hiveflow/cli.py` | 添加 blend_app、perf_app 及所有命令 |

---

## Chunk 1: Phase 1 — Portfolio Blend

### Task 1: BlendConfig 实体 + DB 注册

**Files:**
- Create: `src/hiveflow/domain/blend_configs.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_blend.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_blend.py
"""Blend CRUD 测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.blend_configs import BlendConfig


def _settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db")


def test_blend_config_create_and_read(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    record = BlendConfig(
        name="my_blend",
        strategy_names=json.dumps(["MomentumStrategy", "EqualWeightStrategy"]),
        weights=json.dumps({"MomentumStrategy": 0.6, "EqualWeightStrategy": 0.4}),
        auto_optimized=False,
        optimize_metric="sharpe",
    )
    with get_session(settings) as session:
        session.add(record)
        session.commit()
        session.refresh(record)
        assert record.id is not None
        assert record.name == "my_blend"
        assert json.loads(record.strategy_names) == ["MomentumStrategy", "EqualWeightStrategy"]
        assert record.optimize_metric == "sharpe"
        assert record.created_at is not None
        assert record.updated_at is not None
```

- [ ] **Step 2: 运行确认失败**

```
uv run python -m pytest tests/test_blend.py::test_blend_config_create_and_read -v
```
预期：`ModuleNotFoundError: No module named 'hiveflow.domain.blend_configs'`

- [ ] **Step 3: 创建实体文件**

```python
# src/hiveflow/domain/blend_configs.py
"""多策略混合配置领域模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class BlendConfig(SQLModel, table=True):
    """多策略混合配置：记录参与混合的策略名称、权重及自动优化设置。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(sa_column=Column(String, unique=True))  # DB 级唯一约束
    strategy_names: str          # JSON list，如 ["MomentumStrategy", "EqualWeightStrategy"]
    weights: str                 # JSON dict，如 {"MomentumStrategy": 0.6, "EqualWeightStrategy": 0.4}
    auto_optimized: bool         # True = 运行时自动计算权重；False = 使用手动权重
    optimize_metric: str = Field(default="sharpe")  # "sharpe" | "calmar" | "return"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    # 注：updated_at 由 Application 层在每次 blend run 后手动更新
```

- [ ] **Step 4: 在 db.py 注册新实体**

在 `src/hiveflow/db.py` 的 import 块中（`from hiveflow.domain.strategy_runs import StrategyRun` 那行后面）添加：

```python
from hiveflow.domain.blend_configs import BlendConfig  # noqa: F401
```

- [ ] **Step 5: 运行确认通过**

```
uv run python -m pytest tests/test_blend.py::test_blend_config_create_and_read -v
```
预期：`PASSED`

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/domain/blend_configs.py src/hiveflow/db.py tests/test_blend.py
git commit -m "feat: 新增 BlendConfig 实体与 DB 注册"
```

---

### Task 2: Blend Application 服务

**Files:**
- Create: `src/hiveflow/application/blend.py`
- Modify: `tests/test_blend.py`

- [ ] **Step 1: 写失败测试（重名保护 + 手动权重归一化）**

在 `tests/test_blend.py` 末尾追加：

```python
from hiveflow.application.blend import (
    create_blend,
    list_blends,
    run_blend,
    BlendRunResult,
)


def test_create_blend_manual_weights(tmp_path):
    settings = _settings(tmp_path)
    cfg = create_blend(
        name="manual",
        strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
        weights=[0.6, 0.4],
        optimize_metric="sharpe",
        settings=settings,
    )
    assert cfg.name == "manual"
    assert cfg.auto_optimized is False
    parsed = json.loads(cfg.weights)
    assert abs(parsed["MomentumStrategy"] - 0.6) < 1e-9
    assert abs(parsed["EqualWeightStrategy"] - 0.4) < 1e-9


def test_create_blend_auto_weights(tmp_path):
    settings = _settings(tmp_path)
    cfg = create_blend(
        name="auto",
        strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
        weights=None,  # 自动
        optimize_metric="sharpe",
        settings=settings,
    )
    assert cfg.auto_optimized is True


def test_create_blend_duplicate_name_raises(tmp_path):
    settings = _settings(tmp_path)
    create_blend(
        name="dup",
        strategy_names=["MomentumStrategy"],
        weights=None,
        optimize_metric="sharpe",
        settings=settings,
    )
    with pytest.raises(ValueError, match="已存在"):
        create_blend(
            name="dup",
            strategy_names=["EqualWeightStrategy"],
            weights=None,
            optimize_metric="sharpe",
            settings=settings,
        )


def test_create_blend_weights_not_normalized_raises(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="权重之和"):
        create_blend(
            name="bad",
            strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
            weights=[0.5, 0.3],  # 不等于 1.0
            optimize_metric="sharpe",
            settings=settings,
        )


def test_list_blends(tmp_path):
    settings = _settings(tmp_path)
    create_blend("b1", ["MomentumStrategy"], None, "sharpe", settings=settings)
    create_blend("b2", ["EqualWeightStrategy"], None, "calmar", settings=settings)
    blends = list_blends(settings=settings)
    assert len(blends) == 2
    names = [b.name for b in blends]
    assert "b1" in names and "b2" in names
```

- [ ] **Step 2: 运行确认失败**

```
uv run python -m pytest tests/test_blend.py -k "create_blend or list_blends" -v
```
预期：`ImportError` 或 `ModuleNotFoundError`

- [ ] **Step 3: 实现 create_blend 和 list_blends**

```python
# src/hiveflow/application/blend.py
"""多策略混合应用服务。"""
from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.blend_configs import BlendConfig
from hiveflow.domain.common import utc_now


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
```

- [ ] **Step 4: 运行确认通过**

```
uv run python -m pytest tests/test_blend.py -k "create_blend or list_blends" -v
```
预期：5 个测试全 `PASSED`

- [ ] **Step 5: 写 run_blend 失败测试**

在 `tests/test_blend.py` 末尾追加：

```python
from hiveflow.domain.strategy_runs import StrategyRun
from hiveflow.domain.backtests import BacktestResult


def _seed_strategy_run(
    session, strategy_name: str, weights: dict
) -> StrategyRun:
    import json as _json
    run = StrategyRun(
        strategy_name=strategy_name,
        params=_json.dumps({}),
        weights=_json.dumps(weights),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def _seed_backtest(
    session, strategy_name: str, sharpe: float, total_return: float, max_drawdown: float
) -> BacktestResult:
    bt = BacktestResult(
        strategy_name=strategy_name,
        prices_file="test.csv",
        periods=90,
        total_return=total_return,
        max_drawdown=max_drawdown,
        sharpe=sharpe,
    )
    session.add(bt)
    session.commit()
    session.refresh(bt)
    return bt


def test_run_blend_manual_weights(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    with get_session(settings) as session:
        _seed_strategy_run(session, "MomentumStrategy", {"BTC": 0.7, "ETH": 0.3})
        _seed_strategy_run(session, "EqualWeightStrategy", {"BTC": 0.5, "ETH": 0.5})

    create_blend(
        name="manual_run",
        strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
        weights=[0.6, 0.4],
        optimize_metric="sharpe",
        settings=settings,
    )

    result = run_blend(name="manual_run", apply=False, settings=settings)

    assert result.name == "manual_run"
    # 期望资产权重：BTC = 0.6*0.7 + 0.4*0.5 = 0.62, ETH = 0.6*0.3 + 0.4*0.5 = 0.38
    assert abs(result.asset_weights["BTC"] - 0.62) < 1e-9
    assert abs(result.asset_weights["ETH"] - 0.38) < 1e-9
    assert result.applied is False


def test_run_blend_auto_weights_by_sharpe(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    with get_session(settings) as session:
        _seed_strategy_run(session, "MomentumStrategy", {"BTC": 1.0})
        _seed_strategy_run(session, "EqualWeightStrategy", {"BTC": 1.0})
        _seed_backtest(session, "MomentumStrategy", sharpe=2.0, total_return=0.5, max_drawdown=-0.2)
        _seed_backtest(session, "EqualWeightStrategy", sharpe=1.0, total_return=0.3, max_drawdown=-0.1)

    create_blend(
        name="auto_sharpe",
        strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
        weights=None,  # 自动
        optimize_metric="sharpe",
        settings=settings,
    )

    result = run_blend(name="auto_sharpe", apply=False, settings=settings)

    # sharpe: 2.0 + 1.0 = 3.0; Momentum = 2/3 ≈ 0.667, Equal = 1/3 ≈ 0.333
    assert abs(result.blend_weights["MomentumStrategy"] - 2 / 3) < 1e-9
    assert abs(result.blend_weights["EqualWeightStrategy"] - 1 / 3) < 1e-9


def test_run_blend_fallback_equal_weight_when_no_backtest(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    with get_session(settings) as session:
        _seed_strategy_run(session, "MomentumStrategy", {"BTC": 1.0})
        _seed_strategy_run(session, "EqualWeightStrategy", {"BTC": 1.0})
        # 故意不插入 BacktestResult

    create_blend(
        name="no_bt",
        strategy_names=["MomentumStrategy", "EqualWeightStrategy"],
        weights=None,
        optimize_metric="sharpe",
        settings=settings,
    )

    result = run_blend(name="no_bt", apply=False, settings=settings)

    # 等权回退
    assert abs(result.blend_weights["MomentumStrategy"] - 0.5) < 1e-9
    assert abs(result.blend_weights["EqualWeightStrategy"] - 0.5) < 1e-9


def test_run_blend_apply_writes_target_allocation(tmp_path):
    from hiveflow.domain.allocations import TargetAllocation
    from sqlmodel import select as _select

    settings = _settings(tmp_path)
    create_all_tables(settings)

    with get_session(settings) as session:
        _seed_strategy_run(session, "MomentumStrategy", {"BTC": 0.6, "ETH": 0.4})

    create_blend("to_apply", ["MomentumStrategy"], [1.0], "sharpe", settings=settings)
    result = run_blend(name="to_apply", apply=True, settings=settings)

    assert result.applied is True
    with get_session(settings) as session:
        rows = session.exec(
            _select(TargetAllocation).where(
                TargetAllocation.strategy_name == "blend:to_apply"
            )
        ).all()
    symbols = {r.symbol for r in rows}
    assert "BTC" in symbols and "ETH" in symbols
```

- [ ] **Step 6: 运行确认失败**

```
uv run python -m pytest tests/test_blend.py -k "run_blend" -v
```
预期：`ImportError` 或 `AttributeError`

- [ ] **Step 7: 实现 run_blend（追加到 blend.py）**

在 `src/hiveflow/application/blend.py` 中添加以下导入和函数：

```python
# 在文件顶部 import 块追加：
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.decision_logs import DecisionLog
from hiveflow.domain.strategy_runs import StrategyRun
from sqlmodel import delete


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
```

- [ ] **Step 8: 运行确认通过**

```
uv run python -m pytest tests/test_blend.py -v
```
预期：全部 `PASSED`

- [ ] **Step 9: 全量回归**

```
uv run python -m pytest -q
```
预期：无新增失败

- [ ] **Step 10: 提交**

```bash
git add src/hiveflow/application/blend.py tests/test_blend.py
git commit -m "feat: 新增 blend 应用服务（create/list/run/auto-optimize）"
```

---

### Task 3: Blend CLI 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Create: `tests/test_blend_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_blend_cli.py
"""CLI 集成测试：hiveflow quant blend。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner
from unittest.mock import patch

from hiveflow.cli import app
from hiveflow.application.blend import BlendConfigView, BlendRunResult

runner = CliRunner()


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/test.db"


def _view(name: str = "test") -> BlendConfigView:
    return BlendConfigView(
        id=1, name=name,
        strategy_names=["MomentumStrategy"],
        weights={"MomentumStrategy": 1.0},
        auto_optimized=False, optimize_metric="sharpe",
        created_at="2026-03-18T00:00:00+00:00",
        updated_at="2026-03-18T00:00:00+00:00",
    )


def _run_result(name: str = "test") -> BlendRunResult:
    return BlendRunResult(
        name=name,
        blend_weights={"MomentumStrategy": 1.0},
        asset_weights={"BTC": 0.6, "ETH": 0.4},
        applied=False,
    )


def test_blend_create_command(tmp_path):
    with patch("hiveflow.cli.create_blend", return_value=_view()) as mock_fn:
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "create", "test",
            "--strategies", "MomentumStrategy",
        ])
    assert result.exit_code == 0, result.output
    assert mock_fn.called


def test_blend_create_with_weights(tmp_path):
    with patch("hiveflow.cli.create_blend", return_value=_view()) as mock_fn:
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "create", "test2",
            "--strategies", "MomentumStrategy,EqualWeightStrategy",
            "--weights", "0.6,0.4",
        ])
    assert result.exit_code == 0, result.output
    call_kwargs = mock_fn.call_args
    assert call_kwargs is not None


def test_blend_list_command(tmp_path):
    with patch("hiveflow.cli.list_blends", return_value=[_view("b1"), _view("b2")]):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "list",
        ])
    assert result.exit_code == 0, result.output
    assert "b1" in result.output
    assert "b2" in result.output


def test_blend_list_json_output(tmp_path):
    with patch("hiveflow.cli.list_blends", return_value=[_view()]):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "list", "--output", "json",
        ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["name"] == "test"


def test_blend_show_command(tmp_path):
    with patch("hiveflow.cli.get_blend", return_value=_view()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "show", "test",
        ])
    assert result.exit_code == 0, result.output
    assert "test" in result.output


def test_blend_run_command(tmp_path):
    with patch("hiveflow.cli.run_blend", return_value=_run_result()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "run", "test",
        ])
    assert result.exit_code == 0, result.output
    assert "BTC" in result.output


def test_blend_run_json_output(tmp_path):
    with patch("hiveflow.cli.run_blend", return_value=_run_result()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "quant", "blend", "run", "test",
            "--output", "json",
        ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "asset_weights" in data
    assert "blend_weights" in data
```

- [ ] **Step 2: 运行确认失败**

```
uv run python -m pytest tests/test_blend_cli.py -v
```
预期：失败（命令不存在）

- [ ] **Step 3: 在 cli.py 中添加 blend 子命令**

在 `src/hiveflow/cli.py` 中进行以下修改：

**3a. 在 imports 处添加（与其他 application imports 在一起）：**

```python
from hiveflow.application.blend import (
    BlendConfigView,
    BlendRunResult,
    create_blend,
    get_blend,
    list_blends,
    run_blend,
)
```

**3b. 在 `quant_app = typer.Typer(...)` 那行之后添加：**

```python
blend_app = typer.Typer(help="多策略混合命令。")
```

**3c. 在 `app.add_typer(quant_app, name="quant")` 那行之前添加：**

```python
quant_app.add_typer(blend_app, name="blend")
```

**3d. 在 `@quant_app.command("history")` 命令之后（Chunk 1 末尾）添加 blend 命令：**

```python
@blend_app.command("create")
def blend_create(
    name: str = typer.Argument(..., help="Blend 配置名称（唯一）"),
    strategies: str = typer.Option(..., "--strategies", help="逗号分隔的策略名称，如 MomentumStrategy,EqualWeightStrategy"),
    weights: str | None = typer.Option(None, "--weights", help="逗号分隔的手动权重（可选），如 0.6,0.4"),
    optimize_metric: str = typer.Option("sharpe", "--optimize-metric", help="自动优化指标：sharpe | calmar | return"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """创建多策略混合配置。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    strategy_list = [s.strip() for s in strategies.split(",")]
    weight_list = [float(w.strip()) for w in weights.split(",")] if weights else None
    try:
        cfg = create_blend(
            name=name,
            strategy_names=strategy_list,
            weights=weight_list,
            optimize_metric=optimize_metric,
            settings=settings,
        )
    except ValueError as e:
        console.print(f"[red]错误：{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]Blend 配置 '{cfg.name}' 已创建（auto_optimized={cfg.auto_optimized}）[/green]")


@blend_app.command("list")
def blend_list(
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """列出所有 blend 配置。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    blends = list_blends(settings=settings)
    if output == "json":
        console.print(json.dumps([b.to_dict() for b in blends], ensure_ascii=False))
        return
    if not blends:
        console.print("[yellow]暂无 blend 配置。[/yellow]")
        return
    table = Table(title="Blend 配置列表", box=box.SIMPLE)
    table.add_column("ID", style="dim")
    table.add_column("名称", style="bold")
    table.add_column("策略", style="cyan")
    table.add_column("自动优化")
    table.add_column("指标")
    table.add_column("更新时间", style="dim")
    for b in blends:
        table.add_row(
            str(b.id),
            b.name,
            ", ".join(b.strategy_names),
            "✓" if b.auto_optimized else "手动",
            b.optimize_metric,
            b.updated_at[:19],
        )
    console.print(table)


@blend_app.command("show")
def blend_show(
    name: str = typer.Argument(..., help="Blend 配置名称"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """显示 blend 配置详情。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        cfg = get_blend(name=name, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if output == "json":
        console.print(json.dumps(cfg.to_dict(), ensure_ascii=False))
        return
    console.print(Panel(
        f"[bold]{cfg.name}[/bold]\n"
        f"策略：{', '.join(cfg.strategy_names)}\n"
        f"自动优化：{'是' if cfg.auto_optimized else '否'}（指标：{cfg.optimize_metric}）\n"
        f"当前权重：{json.dumps(cfg.weights, ensure_ascii=False)}\n"
        f"创建：{cfg.created_at[:19]}  更新：{cfg.updated_at[:19]}",
        title="Blend 配置",
    ))


@blend_app.command("run")
def blend_run(
    name: str = typer.Argument(..., help="Blend 配置名称"),
    apply: bool = typer.Option(False, "--apply", help="写入 TargetAllocation"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format, help="pretty | json"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """执行 blend：计算混合后资产权重，可选写入目标配比。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        result = run_blend(name=name, apply=apply, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False))
        return
    table = Table(title=f"Blend '{result.name}' 资产权重", box=box.SIMPLE)
    table.add_column("资产", style="bold")
    table.add_column("权重", style="cyan")
    for symbol, w in sorted(result.asset_weights.items(), key=lambda x: -x[1]):
        table.add_row(symbol, f"{w:.4f}")
    console.print(table)
    if result.applied:
        console.print("[green]已写入 TargetAllocation[/green]")
```

- [ ] **Step 4: 运行确认通过**

```
uv run python -m pytest tests/test_blend_cli.py -v
```
预期：全部 `PASSED`

- [ ] **Step 5: 全量回归**

```
uv run python -m pytest -q
```
预期：无新增失败

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/cli.py tests/test_blend_cli.py
git commit -m "feat: 新增 quant blend CLI 命令组（create/list/show/run）"
```

---

## Chunk 2: Phase 2 — 实盘绩效追踪

### Task 4: PortfolioSnapshot 实体 + DB 注册

**Files:**
- Create: `src/hiveflow/domain/portfolio_snapshots.py`
- Modify: `src/hiveflow/db.py`
- Create: `tests/test_perf.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_perf.py
"""Perf 追踪测试。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.portfolio_snapshots import PortfolioSnapshot


def _settings(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path}/test.db")


def test_portfolio_snapshot_create_and_read(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    snap = PortfolioSnapshot(
        total_value_usd=10000.0,
        positions_json=json.dumps({"BTC": 0.6, "ETH": 0.4}),
        source="manual",
    )
    with get_session(settings) as session:
        session.add(snap)
        session.commit()
        session.refresh(snap)
        assert snap.id is not None
        assert snap.total_value_usd == 10000.0
        assert snap.source == "manual"
        assert snap.timestamp is not None
```

- [ ] **Step 2: 运行确认失败**

```
uv run python -m pytest tests/test_perf.py::test_portfolio_snapshot_create_and_read -v
```
预期：`ModuleNotFoundError`

- [ ] **Step 3: 创建实体文件**

```python
# src/hiveflow/domain/portfolio_snapshots.py
"""组合持仓快照领域模型。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from hiveflow.domain.common import utc_now


class PortfolioSnapshot(SQLModel, table=True):
    """组合持仓快照：记录某时刻总持仓价值及各资产快照。"""

    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=utc_now)
    total_value_usd: float       # 总持仓价值（USD）
    positions_json: str          # 持仓快照，JSON，如 {"BTC": {"qty": 0.5, "value_usd": 5000}}
    source: str = Field(default="manual")  # "manual" | "cron"
    notes: Optional[str] = None
```

- [ ] **Step 4: 在 db.py 注册**

在 `src/hiveflow/db.py` 中，在 `from hiveflow.domain.blend_configs import BlendConfig` 后添加：

```python
from hiveflow.domain.portfolio_snapshots import PortfolioSnapshot  # noqa: F401
```

- [ ] **Step 5: 运行确认通过**

```
uv run python -m pytest tests/test_perf.py::test_portfolio_snapshot_create_and_read -v
```
预期：`PASSED`

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/domain/portfolio_snapshots.py src/hiveflow/db.py tests/test_perf.py
git commit -m "feat: 新增 PortfolioSnapshot 实体与 DB 注册"
```

---

### Task 5: Perf Application 服务

**Files:**
- Create: `src/hiveflow/application/perf.py`
- Modify: `tests/test_perf.py`

- [ ] **Step 1: 写失败测试（snapshot + list + compare）**

在 `tests/test_perf.py` 末尾追加：

```python
from hiveflow.application.perf import (
    list_snapshots,
    compare_with_backtest,
    PerfCompareResult,
    PortfolioSnapshotView,
    record_snapshot,
)
from hiveflow.domain.backtests import BacktestResult


def _seed_backtest_with_curve(session, curve: list[float]) -> BacktestResult:
    import json as _json
    bt = BacktestResult(
        strategy_name="MomentumStrategy",
        prices_file="test.csv",
        periods=len(curve) - 1,
        total_return=curve[-1] / curve[0] - 1.0,
        max_drawdown=-0.1,
        sharpe=1.5,
        equity_curve=_json.dumps(curve),
    )
    session.add(bt)
    session.commit()
    session.refresh(bt)
    return bt


def _seed_snapshots(session, values: list[float], base_dt: datetime | None = None) -> None:
    if base_dt is None:
        base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, v in enumerate(values):
        snap = PortfolioSnapshot(
            timestamp=base_dt + timedelta(days=i),
            total_value_usd=v,
            positions_json=json.dumps({}),
            source="manual",
        )
        session.add(snap)
    session.commit()


def test_record_snapshot(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    positions_data = {"BTC": {"qty": 0.5, "value_usd": 5000.0}}
    view = record_snapshot(
        total_value_usd=10000.0,
        positions_data=positions_data,
        source="manual",
        settings=settings,
    )
    assert view.total_value_usd == 10000.0
    assert view.source == "manual"
    assert view.id is not None


def test_list_snapshots(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)
    with get_session(settings) as session:
        _seed_snapshots(session, [10000.0, 10200.0, 10500.0])

    views = list_snapshots(settings=settings)
    assert len(views) == 3
    # 最新在前
    assert views[0].total_value_usd == 10500.0


def test_compare_with_backtest_metrics(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    backtest_curve = [1.0, 1.05, 1.10, 1.08, 1.15]
    live_values = [10000.0, 10300.0, 10600.0, 10500.0, 10800.0]
    base_dt = datetime(2026, 1, 1, tzinfo=timezone.utc)

    with get_session(settings) as session:
        bt = _seed_backtest_with_curve(session, backtest_curve)
        _seed_snapshots(session, live_values, base_dt)

    result = compare_with_backtest(backtest_id=bt.id, settings=settings)

    # 总收益率
    expected_live_return = 10800.0 / 10000.0 - 1.0  # 0.08
    assert abs(result.live_total_return - expected_live_return) < 1e-9
    assert abs(result.backtest_total_return - (1.15 / 1.0 - 1.0)) < 1e-9

    # 年化收益率：快照 4 天跨度（Jan 1 → Jan 4），公式 (1+r)^(365/days)-1
    days = 3  # timedelta between Jan 1 and Jan 4 = 3 days
    expected_annual = (1 + expected_live_return) ** (365 / days) - 1
    assert result.live_annual_return is not None
    assert abs(result.live_annual_return - expected_annual) < 1e-6

    # MDD 为非正
    assert result.live_mdd <= 0.0
    assert result.backtest_mdd <= 0.0
    # Sparkline 存在
    assert len(result.live_sparkline) > 0
    assert len(result.backtest_sparkline) > 0


def test_compare_insufficient_snapshots_returns_na(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)

    backtest_curve = [1.0, 1.05]
    with get_session(settings) as session:
        bt = _seed_backtest_with_curve(session, backtest_curve)
        # 只有 1 条快照
        _seed_snapshots(session, [10000.0])

    result = compare_with_backtest(backtest_id=bt.id, settings=settings)

    assert result.live_annual_return is None  # N/A
    assert result.live_total_return is not None  # 仍有总收益率（单条时为 0）


def test_compare_nonexistent_backtest_raises(tmp_path):
    settings = _settings(tmp_path)
    create_all_tables(settings)
    with pytest.raises(ValueError, match="不存在"):
        compare_with_backtest(backtest_id=9999, settings=settings)
```

- [ ] **Step 2: 运行确认失败**

```
uv run python -m pytest tests/test_perf.py -k "record_snapshot or list_snapshots or compare" -v
```
预期：`ImportError`

- [ ] **Step 3: 实现 perf.py**

```python
# src/hiveflow/application/perf.py
"""实盘绩效追踪应用服务。"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Optional

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.portfolio_snapshots import PortfolioSnapshot

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _sparkline(curve: list[float], width: int = 40) -> str:
    """将序列降采样到至多 width 个字符（与 cli.py 同算法的独立副本，无跨层依赖）。"""
    if not curve or len(curve) < 2:
        return "─" * width
    step = max(1, -(-len(curve) // width))
    sampled = [
        sum(curve[i: i + step]) / len(curve[i: i + step])
        for i in range(0, len(curve), step)
    ][:width]
    lo, hi = min(sampled), max(sampled)
    if lo == hi:
        return _SPARK_CHARS[0] * len(sampled)
    bucket = (hi - lo) / (len(_SPARK_CHARS) - 1)
    return "".join(
        _SPARK_CHARS[min(int((v - lo) / bucket), len(_SPARK_CHARS) - 1)]
        for v in sampled
    )


def _compute_mdd(curve: list[float]) -> float:
    """从价值序列计算最大回撤（非正数）。"""
    if len(curve) < 2:
        return 0.0
    peak = curve[0]
    max_dd = 0.0
    for v in curve:
        if v > peak:
            peak = v
        if peak > 0:
            dd = v / peak - 1.0
            if dd < max_dd:
                max_dd = dd
    return max_dd


@dataclass(frozen=True)
class PortfolioSnapshotView:
    id: int | None
    timestamp: str
    total_value_usd: float
    source: str
    notes: str | None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "total_value_usd": self.total_value_usd,
            "source": self.source,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class PerfCompareResult:
    backtest_id: int
    live_sparkline: str
    backtest_sparkline: str
    live_total_return: float
    backtest_total_return: float
    live_annual_return: float | None    # None = 快照不足 2 条或 days==0
    backtest_annual_return: float | None
    live_mdd: float
    backtest_mdd: float
    snapshot_count: int

    def to_dict(self) -> dict:
        return {
            "backtest_id": self.backtest_id,
            "live_sparkline": self.live_sparkline,
            "backtest_sparkline": self.backtest_sparkline,
            "live_total_return": self.live_total_return,
            "backtest_total_return": self.backtest_total_return,
            "live_annual_return": self.live_annual_return,
            "backtest_annual_return": self.backtest_annual_return,
            "live_mdd": self.live_mdd,
            "backtest_mdd": self.backtest_mdd,
            "snapshot_count": self.snapshot_count,
        }


def record_snapshot(
    total_value_usd: float,
    positions_data: dict,
    source: str = "manual",
    notes: str | None = None,
    settings: Settings | None = None,
) -> PortfolioSnapshotView:
    """记录一次组合快照。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    snap = PortfolioSnapshot(
        total_value_usd=total_value_usd,
        positions_json=json.dumps(positions_data),
        source=source,
        notes=notes,
    )
    with get_session(app_settings) as session:
        session.add(snap)
        session.commit()
        session.refresh(snap)

    return _to_view(snap)


def list_snapshots(
    limit: int = 20,
    settings: Settings | None = None,
) -> list[PortfolioSnapshotView]:
    """查询历史快照（最新在前）。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    with get_session(app_settings) as session:
        rows = session.exec(
            select(PortfolioSnapshot)
            .order_by(PortfolioSnapshot.timestamp.desc())
            .limit(limit)
        ).all()

    return [_to_view(r) for r in rows]


def compare_with_backtest(
    backtest_id: int,
    settings: Settings | None = None,
) -> PerfCompareResult:
    """对比实盘快照权益曲线与指定回测权益曲线，返回 Sparkline + 指标。"""
    from hiveflow.domain.backtests import BacktestResult

    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 加载回测
    with get_session(app_settings) as session:
        bt = session.get(BacktestResult, backtest_id)
        if bt is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        if bt.equity_curve is None:
            raise ValueError(f"回测 #{backtest_id} 无 equity_curve 数据，请重新运行回测。")
        backtest_curve: list[float] = json.loads(bt.equity_curve)

    # 加载快照（按时间升序）
    with get_session(app_settings) as session:
        snaps = session.exec(
            select(PortfolioSnapshot).order_by(PortfolioSnapshot.timestamp.asc())
        ).all()

    live_values = [s.total_value_usd for s in snaps]
    n_snaps = len(live_values)

    # 归一化实盘曲线到 1.0 起点
    if n_snaps >= 1:
        first_val = live_values[0]
        live_curve = [v / first_val for v in live_values] if first_val > 0 else live_values
    else:
        live_curve = [1.0]

    # 计算实盘指标
    if n_snaps >= 2:
        live_total_return = live_curve[-1] - 1.0
        days = (snaps[-1].timestamp - snaps[0].timestamp).days
        if days > 0:
            live_annual_return: Optional[float] = (1 + live_total_return) ** (365 / days) - 1
        else:
            live_annual_return = None
    else:
        live_total_return = 0.0
        live_annual_return = None

    live_mdd = _compute_mdd(live_curve)

    # 计算回测指标
    bt_total_return = backtest_curve[-1] / backtest_curve[0] - 1.0
    bt_mdd = _compute_mdd(backtest_curve)
    bt_days = len(backtest_curve) - 1
    if bt_days > 0:
        bt_annual_return: Optional[float] = (1 + bt_total_return) ** (365 / bt_days) - 1
    else:
        bt_annual_return = None

    return PerfCompareResult(
        backtest_id=backtest_id,
        live_sparkline=_sparkline(live_curve),
        backtest_sparkline=_sparkline(backtest_curve),
        live_total_return=live_total_return,
        backtest_total_return=bt_total_return,
        live_annual_return=live_annual_return,
        backtest_annual_return=bt_annual_return,
        live_mdd=live_mdd,
        backtest_mdd=bt_mdd,
        snapshot_count=n_snaps,
    )


def _to_view(snap: PortfolioSnapshot) -> PortfolioSnapshotView:
    return PortfolioSnapshotView(
        id=snap.id,
        timestamp=snap.timestamp.isoformat(),
        total_value_usd=snap.total_value_usd,
        source=snap.source,
        notes=snap.notes,
    )
```

- [ ] **Step 4: 运行确认通过**

```
uv run python -m pytest tests/test_perf.py -v
```
预期：全部 `PASSED`

- [ ] **Step 5: 全量回归**

```
uv run python -m pytest -q
```
预期：无新增失败

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/application/perf.py tests/test_perf.py
git commit -m "feat: 新增 perf 应用服务（record_snapshot/list/compare）"
```

---

### Task 6: Perf CLI 命令 + cron 配置

**Files:**
- Modify: `src/hiveflow/cli.py`
- Create: `config/tracking.json`
- Create: `tests/test_perf_cli.py`

- [ ] **Step 1: 创建 cron 配置模板**

```json
{
  "snapshot_interval": "1h",
  "auto_sync_positions": true,
  "_intervals": {
    "1h": "0 * * * *",
    "6h": "0 */6 * * *",
    "daily": "0 9 * * *"
  },
  "_comment": "snapshot_interval 支持 1h / 6h / daily。修改后重新运行 hiveflow perf setup-cron 生效。"
}
```

保存到：`config/tracking.json`

- [ ] **Step 2: 写失败测试**

```python
# tests/test_perf_cli.py
"""CLI 集成测试：hiveflow perf。"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from hiveflow.cli import app
from hiveflow.application.perf import (
    PortfolioSnapshotView,
    PerfCompareResult,
)

runner = CliRunner()


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/test.db"


def _snap_view(i: int = 1) -> PortfolioSnapshotView:
    return PortfolioSnapshotView(
        id=i,
        timestamp="2026-03-18T10:00:00+00:00",
        total_value_usd=10000.0 + i * 100,
        source="manual",
        notes=None,
    )


def _compare_result() -> PerfCompareResult:
    return PerfCompareResult(
        backtest_id=1,
        live_sparkline="▁▂▃▄▅",
        backtest_sparkline="▂▃▄▅▆",
        live_total_return=0.08,
        backtest_total_return=0.15,
        live_annual_return=0.32,
        backtest_annual_return=0.55,
        live_mdd=-0.05,
        backtest_mdd=-0.10,
        snapshot_count=10,
    )


def test_perf_snapshot_command(tmp_path, monkeypatch):
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.take_perf_snapshot", return_value=_snap_view()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "perf", "snapshot",
        ])
    assert result.exit_code == 0, result.output
    assert "10100" in result.output


def test_perf_snapshot_requires_okx_credentials(tmp_path, monkeypatch):
    # 确保环境变量不存在（隔离开发环境中可能设置的真实 Key）
    for key in ("HIVEFLOW_OKX_API_KEY", "HIVEFLOW_OKX_API_SECRET", "HIVEFLOW_OKX_API_PASSPHRASE"):
        monkeypatch.delenv(key, raising=False)
    result = runner.invoke(app, [
        "--database-url", _db_url(tmp_path),
        "perf", "snapshot",
    ])
    assert result.exit_code == 1
    assert "OKX_API_KEY" in result.output


def test_perf_list_command(tmp_path):
    with patch("hiveflow.cli.list_snapshots", return_value=[_snap_view(1), _snap_view(2)]):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "perf", "list",
        ])
    assert result.exit_code == 0, result.output
    assert "10100" in result.output


def test_perf_list_json_output(tmp_path):
    with patch("hiveflow.cli.list_snapshots", return_value=[_snap_view()]):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "perf", "list", "--output", "json",
        ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data[0]["source"] == "manual"


def test_perf_compare_command(tmp_path):
    with patch("hiveflow.cli.compare_with_backtest", return_value=_compare_result()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "perf", "compare", "1",
        ])
    assert result.exit_code == 0, result.output
    assert "▁▂▃▄▅" in result.output
    assert "8.00%" in result.output


def test_perf_compare_json_output(tmp_path):
    with patch("hiveflow.cli.compare_with_backtest", return_value=_compare_result()):
        result = runner.invoke(app, [
            "--database-url", _db_url(tmp_path),
            "perf", "compare", "1", "--output", "json",
        ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "live_sparkline" in data
    assert data["backtest_id"] == 1


def test_perf_setup_cron_output(tmp_path):
    result = runner.invoke(app, [
        "--database-url", _db_url(tmp_path),
        "perf", "setup-cron", "--dry-run",
    ])
    assert result.exit_code == 0, result.output
    # 验证 crontab 字符串格式（含 hiveflow perf snapshot）
    assert "hiveflow perf snapshot" in result.output
    assert "*" in result.output
```

- [ ] **Step 3: 运行确认失败**

```
uv run python -m pytest tests/test_perf_cli.py -v
```
预期：失败（命令不存在）

- [ ] **Step 4: 在 cli.py 中添加 perf 命令**

**4a. 在 imports 处添加：**

```python
from hiveflow.application.perf import (
    PerfCompareResult,
    PortfolioSnapshotView,
    compare_with_backtest,
    list_snapshots,
    record_snapshot as _record_snapshot_impl,
)
```

**4b. 在 `risk_analysis_app = typer.Typer(...)` 那行后面添加：**

```python
perf_app = typer.Typer(help="实盘绩效追踪命令。")
```

**4c. 在 `app.add_typer(risk_analysis_app, name="risk-analysis")` 后面添加：**

```python
app.add_typer(perf_app, name="perf")
```

**4d. 在文件末尾 `app.add_typer` 块之后添加 perf 命令和一个包装函数：**

> 注意：`record_snapshot` 已通过步骤 4a 以别名 `_record_snapshot_impl` 导入，此处直接使用，无需重复导入。

```python
def take_perf_snapshot(
    api_key: str,
    api_secret: str,
    passphrase: str,
    source: str = "manual",
    settings: Settings | None = None,
) -> PortfolioSnapshotView:
    """从 OKX 获取最新持仓，计算总价值，存入快照。可 mock 用于测试。"""
    from hiveflow.domain.positions import Position
    provider = OkxProvider(api_key=api_key, api_secret=api_secret, passphrase=passphrase)
    positions = provider.fetch_positions()
    total_value = sum(p.market_value or 0.0 for p in positions)
    positions_data = {
        p.symbol: {"qty": p.qty, "value_usd": p.market_value}
        for p in positions
    }
    return _record_snapshot_impl(
        total_value_usd=total_value,
        positions_data=positions_data,
        source=source,
        settings=settings,
    )


@perf_app.command("snapshot")
def perf_snapshot(
    source: str = typer.Option("manual", "--source", help="manual | cron"),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """记录一次实盘组合快照（从 OKX 同步当前持仓价值）。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    api_key = settings.okx_api_key
    api_secret = settings.okx_api_secret
    passphrase = settings.okx_api_passphrase
    if not api_key or not api_secret or not passphrase:
        console.print(
            "[red]缺少 OKX 凭证，请设置 HIVEFLOW_OKX_API_KEY / "
            "HIVEFLOW_OKX_API_SECRET / HIVEFLOW_OKX_API_PASSPHRASE。[/red]"
        )
        raise typer.Exit(1)
    try:
        view = take_perf_snapshot(
            api_key=api_key,
            api_secret=api_secret,
            passphrase=passphrase,
            source=source,
            settings=settings,
        )
    except Exception as e:
        console.print(f"[red]快照失败：{e}[/red]")
        raise typer.Exit(1)
    console.print(
        f"[green]快照已记录：总价值 {view.total_value_usd:,.2f} USD "
        f"（{view.timestamp[:19]}）[/green]"
    )


@perf_app.command("list")
def perf_list(
    limit: int = typer.Option(20, "--limit", help="最多显示条数"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """列出历史实盘快照。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    snaps = list_snapshots(limit=limit, settings=settings)
    if output == "json":
        console.print(json.dumps([s.to_dict() for s in snaps], ensure_ascii=False))
        return
    if not snaps:
        console.print("[yellow]暂无快照记录，请先运行 `hiveflow perf snapshot`。[/yellow]")
        return
    table = Table(title="实盘组合快照", box=box.SIMPLE)
    table.add_column("ID", style="dim")
    table.add_column("时间", style="bold")
    table.add_column("总价值（USD）", style="cyan")
    table.add_column("来源")
    table.add_column("备注", style="dim")
    for s in snaps:
        table.add_row(
            str(s.id),
            s.timestamp[:19],
            f"{s.total_value_usd:,.2f}",
            s.source,
            s.notes or "",
        )
    console.print(table)


@perf_app.command("compare")
def perf_compare(
    backtest_id: int = typer.Argument(..., help="回测 ID"),
    output: str = typer.Option("pretty", "--output", callback=_validate_output_format),
    database_url: str | None = typer.Option(None, "--database-url", envvar="HIVEFLOW_DATABASE_URL", hidden=True),
):
    """对比实盘权益曲线与指定回测，输出 Sparkline + 指标。"""
    settings = Settings(database_url=database_url) if database_url else Settings()
    try:
        result = compare_with_backtest(backtest_id=backtest_id, settings=settings)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False))
        return

    # Sparkline 并排
    console.print(f"\n[bold]实盘[/bold] ({result.snapshot_count} 个快照) vs [bold]回测 #{result.backtest_id}[/bold]\n")
    console.print(f"  实盘 : {result.live_sparkline}")
    console.print(f"  回测 : {result.backtest_sparkline}\n")

    # 指标表
    def _fmt_pct(v: float | None) -> str:
        return f"{v * 100:.2f}%" if v is not None else "N/A"

    table = Table(box=box.SIMPLE)
    table.add_column("指标", style="bold")
    table.add_column("实盘", style="cyan")
    table.add_column("回测", style="green")
    table.add_row("总收益率", _fmt_pct(result.live_total_return), _fmt_pct(result.backtest_total_return))
    table.add_row("年化收益率", _fmt_pct(result.live_annual_return), _fmt_pct(result.backtest_annual_return))
    table.add_row("最大回撤", _fmt_pct(result.live_mdd), _fmt_pct(result.backtest_mdd))
    console.print(table)


@perf_app.command("setup-cron")
def perf_setup_cron(
    dry_run: bool = typer.Option(False, "--dry-run", help="只打印 crontab 行，不实际写入"),
    config_path: str = typer.Option("config/tracking.json", "--config", help="追踪配置文件路径"),
):
    """读取 config/tracking.json，安装 perf snapshot 定时任务到系统 crontab。"""
    import subprocess

    config_file = Path(config_path)
    if not config_file.exists():
        console.print(f"[red]配置文件 {config_path} 不存在，请先创建 config/tracking.json。[/red]")
        raise typer.Exit(1)

    tracking_config = json.loads(config_file.read_text())
    interval = tracking_config.get("snapshot_interval", "1h")
    intervals = tracking_config.get("_intervals", {
        "1h": "0 * * * *",
        "6h": "0 */6 * * *",
        "daily": "0 9 * * *",
    })
    cron_schedule = intervals.get(interval, "0 * * * *")

    project_dir = Path.cwd().resolve()
    cron_line = f"{cron_schedule} cd {project_dir} && uv run hiveflow perf snapshot --source cron"

    if dry_run:
        console.print(f"[yellow]（dry-run）生成的 crontab 行：[/yellow]")
        console.print(cron_line)
        return

    # 读取现有 crontab，去重后追加
    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current_lines = existing.stdout.strip().splitlines() if existing.returncode == 0 else []
    # 移除旧的同类行
    current_lines = [l for l in current_lines if "hiveflow perf snapshot" not in l]
    current_lines.append(cron_line)
    new_crontab = "\n".join(current_lines) + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode != 0:
        console.print(f"[red]写入 crontab 失败：{proc.stderr}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]crontab 已更新（间隔：{interval}）：[/green]")
    console.print(cron_line)
```

- [ ] **Step 5: 运行确认通过**

```
uv run python -m pytest tests/test_perf_cli.py -v
```
预期：全部 `PASSED`

- [ ] **Step 6: 全量回归**

```
uv run python -m pytest -q
```
预期：无新增失败

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/cli.py tests/test_perf_cli.py config/tracking.json
git commit -m "feat: 新增 perf CLI 命令组（snapshot/list/compare/setup-cron）+ cron 配置"
```

---

### Task 7: 更新文档

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/ROADMAP.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1: 全量测试（最终确认）**

```
uv run python -m pytest -q
```
预期：全部通过，无失败

- [ ] **Step 2: 更新 CURRENT_STATE.md**

在"已完成阶段"中追加 M9 交付条目，在"当前可用命令"中追加：
- `hiveflow quant blend create / run / list / show`
- `hiveflow perf snapshot / list / compare / setup-cron`

- [ ] **Step 3: 更新 ROADMAP.md**

将 `## M9：下一阶段（规划中）` 改为 `## M9：多策略混合 + 实盘绩效追踪（已完成）`，写入交付内容。

- [ ] **Step 4: 追加 SESSION_LOG.md**

追加：
```
## 2026-03-18
- 决策：M9 选择「多策略混合 + 实盘绩效追踪」，两个功能串联形成 blend→execute→track→compare 链路
- 设计：BlendConfig + PortfolioSnapshot 两个新实体，blend app + perf app 两个新 application 模块
- 结果：全量测试通过，quant blend 和 perf 命令组已上线
```

- [ ] **Step 5: 提交文档**

```bash
git add docs/context/CURRENT_STATE.md docs/context/ROADMAP.md docs/context/SESSION_LOG.md
git commit -m "docs: 更新文档记录 M9 交付"
```
