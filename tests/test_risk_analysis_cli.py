"""风险分析应用层与 CLI 集成测试。"""
from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.market_data import MarketBar


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _seed_market_bars(tmp_path: Path, monkeypatch, symbol_closes: dict[str, list[float]]) -> None:
    """在临时 DB 种入 MarketBar 数据。"""
    from datetime import datetime, timezone
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with get_session() as session:
        for symbol, closes in symbol_closes.items():
            for i, close in enumerate(closes):
                session.add(MarketBar(
                    symbol=symbol,
                    timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=1000.0,
                ))
        session.commit()


def _seed_backtest(tmp_path: Path, monkeypatch, equity_curve=None) -> int:
    """在临时 DB 种入一条 BacktestResult，返回 id。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.15,
            max_drawdown=-0.05,
            sharpe=1.5,
            equity_curve=json.dumps(equity_curve) if equity_curve is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


# ─── Task 4：应用层 ───────────────────────────────────────────────────────────

def test_analyze_asset_risk_basic(tmp_path: Path, monkeypatch) -> None:
    """analyze_asset_risk 返回资产视图列表 + CorrelationView。"""
    from hiveflow.application.risk_analysis import analyze_asset_risk
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0, 110.0],
        "ETH": [50.0, 55.0, 52.0, 57.0, 54.0],
    })
    assets, corr = analyze_asset_risk()
    assert len(assets) == 2
    symbols = [a.symbol for a in assets]
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert corr.symbols == ["BTC", "ETH"]
    assert len(corr.matrix) == 2


def test_analyze_asset_risk_no_data(tmp_path: Path, monkeypatch) -> None:
    """MarketBar 无数据时抛 ValueError。"""
    from hiveflow.application.risk_analysis import analyze_asset_risk
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with pytest.raises(ValueError, match="没有数据"):
        analyze_asset_risk()


def test_analyze_portfolio_risk_basic(tmp_path: Path, monkeypatch) -> None:
    """analyze_portfolio_risk 返回含三个键的 dict。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    curve = [1.0, 1.05, 1.02, 1.1, 1.08, 1.15]
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=curve)
    result = analyze_portfolio_risk(rid)
    assert result is not None
    assert "annual_vol" in result
    assert "win_rate" in result
    assert "calmar_ratio" in result


def test_analyze_portfolio_risk_null_curve(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL 时返回 None（不抛错）。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    rid = _seed_backtest(tmp_path, monkeypatch, equity_curve=None)
    result = analyze_portfolio_risk(rid)
    assert result is None


def test_analyze_portfolio_risk_missing_id(tmp_path: Path, monkeypatch) -> None:
    """ID 不存在时抛 ValueError。"""
    from hiveflow.application.risk_analysis import analyze_portfolio_risk
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    with pytest.raises(ValueError, match="不存在"):
        analyze_portfolio_risk(9999)


# ─── Task 5：risk-analysis assets CLI ────────────────────────────────────────

def test_risk_assets_cli(tmp_path: Path, monkeypatch) -> None:
    """risk-analysis assets exit_code=0，输出含资产名与相关性矩阵标题。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0, 110.0],
        "ETH": [50.0, 55.0, 52.0, 57.0, 54.0],
    })
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets"])
    assert result.exit_code == 0, result.output
    assert "BTC" in result.output
    assert "相关性" in result.output


def test_risk_assets_json(tmp_path: Path, monkeypatch) -> None:
    """--output json 输出含 assets 和 correlation 键的 dict。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    _seed_market_bars(tmp_path, monkeypatch, {
        "BTC": [100.0, 110.0, 105.0, 115.0],
        "ETH": [50.0, 55.0, 52.0, 57.0],
    })
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets", "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "assets" in data
    assert "correlation" in data
    assert isinstance(data["assets"], list)


def test_risk_assets_no_data(tmp_path: Path, monkeypatch) -> None:
    """MarketBar 空时 exit_code=1。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/ra.db")
    create_all_tables()
    runner = CliRunner()
    result = runner.invoke(app, ["risk-analysis", "assets"])
    assert result.exit_code == 1
