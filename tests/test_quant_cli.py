"""CLI 集成测试：hiveflow quant list / run / history。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from hiveflow.cli import app

runner = CliRunner()


def _db_url(tmp_path: Path) -> str:
    return f"sqlite:///{tmp_path}/test.db"


def _seed_market_data(tmp_path: Path, db_url: str):
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar

    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    rng = np.random.default_rng(42)
    base_date = datetime(2025, 1, 1)
    with get_session(settings) as session:
        for i in range(90):
            ts = base_date + timedelta(days=i)
            for sym in ("BTC", "ETH", "USDT"):
                bar = MarketBar(
                    symbol=sym,
                    timestamp=ts,
                    open=float(rng.uniform(90, 110)),
                    high=float(rng.uniform(110, 120)),
                    low=float(rng.uniform(80, 90)),
                    close=float(rng.uniform(90, 110)),
                    volume=1000.0,
                )
                session.add(bar)
        session.commit()


def test_quant_list_shows_builtin_strategies():
    result = runner.invoke(app, ["quant", "list"])
    assert result.exit_code == 0, result.output
    assert "EqualWeightStrategy" in result.output
    assert "MomentumStrategy" in result.output


def test_quant_run_json_output(tmp_path):
    db_url = _db_url(tmp_path)
    _seed_market_data(tmp_path, db_url)
    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run",
        "--strategy", "EqualWeightStrategy",
        "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["strategy"] == "EqualWeightStrategy"
    assert abs(sum(data["weights"].values()) - 1.0) < 1e-9
    assert "run_id" in data


def test_quant_run_param_type_coercion(tmp_path):
    db_url = _db_url(tmp_path)
    _seed_market_data(tmp_path, db_url)
    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run",
        "--strategy", "MomentumStrategy",
        "--param", "lookback_days=14",
        "--param", "min_usdt=0.20",
        "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["params"]["lookback_days"] == 14       # int
    assert abs(data["params"]["min_usdt"] - 0.20) < 1e-9  # float


def test_quant_history_lists_runs(tmp_path):
    db_url = _db_url(tmp_path)
    _seed_market_data(tmp_path, db_url)
    runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run", "--strategy", "EqualWeightStrategy",
    ])
    result = runner.invoke(app, ["--database-url", db_url, "quant", "history"])
    assert result.exit_code == 0, result.output
    assert "EqualWeightStrategy" in result.output


def test_quant_history_json_by_id(tmp_path):
    db_url = _db_url(tmp_path)
    _seed_market_data(tmp_path, db_url)
    run_result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "run", "--strategy", "EqualWeightStrategy", "--output", "json",
    ])
    run_id = json.loads(run_result.output)["run_id"]

    result = runner.invoke(app, [
        "--database-url", db_url,
        "quant", "history", "--id", str(run_id), "--output", "json",
    ])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["id"] == run_id
