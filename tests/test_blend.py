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
