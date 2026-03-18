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
