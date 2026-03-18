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
