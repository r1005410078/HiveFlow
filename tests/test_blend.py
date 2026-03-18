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


from hiveflow.application.blend import (
    create_blend,
    get_blend,
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
    assert abs(cfg.weights["MomentumStrategy"] - 0.6) < 1e-9
    assert abs(cfg.weights["EqualWeightStrategy"] - 0.4) < 1e-9


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


def test_get_blend_not_found_raises(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(ValueError, match="不存在"):
        get_blend(name="nonexistent", settings=settings)
