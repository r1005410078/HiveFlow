# tests/test_blend_cli.py
"""CLI 集成测试：hiveflow quant blend。"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

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
