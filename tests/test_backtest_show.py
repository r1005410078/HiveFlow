"""回测权益曲线可视化测试。"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.backtests import BacktestResult
from hiveflow.services.backtest_engine import (
    BacktestMetrics,
    PriceBar,
    run_dynamic_backtest,
    run_weighted_backtest,
)
from hiveflow.services.strategies.equal_weight import EqualWeightStrategy
from hiveflow.application.backtest import get_backtest_result


# ─── 辅助函数 ────────────────────────────────────────────────────────────────

def _seed_record(tmp_path: Path, monkeypatch, equity_curve=None) -> int:
    """在临时 DB 中种入一条 BacktestResult，返回其 id。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with get_session() as session:
        row = BacktestResult(
            strategy_name="TestStrategy",
            prices_file="DB:MarketBar",
            periods=10,
            total_return=0.12,
            max_drawdown=-0.05,
            sharpe=1.5,
            equity_curve=json.dumps(equity_curve) if equity_curve is not None else None,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _make_bars(symbol: str, closes: list[float]) -> list[PriceBar]:
    return [
        PriceBar(symbol=symbol, timestamp=f"2026-01-{i+1:02d}T00:00:00Z", close=c)
        for i, c in enumerate(closes)
    ]


# ─── Task 1：equity_curve 字段 ────────────────────────────────────────────────

def test_backtest_result_has_equity_curve_field(tmp_path: Path, monkeypatch) -> None:
    """BacktestResult 应有 equity_curve 字段，默认为 None。"""
    rid = _seed_record(tmp_path, monkeypatch)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    with get_session() as session:
        row = session.get(BacktestResult, rid)
        assert hasattr(row, "equity_curve")
        assert row.equity_curve is None


# ─── Task 2：BacktestMetrics.curve ───────────────────────────────────────────

def test_backtest_metrics_has_curve() -> None:
    """BacktestMetrics.curve 应存在，长度 == periods + 1，首值为 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(10)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(10)]),
    }
    weights = {"BTC": 0.6, "ETH": 0.4}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert hasattr(m, "curve")
    assert len(m.curve) == m.periods + 1
    assert m.curve[0] == 1.0


def test_run_weighted_backtest_curve() -> None:
    """上涨序列下 curve[-1] > 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 * (1 + 0.01 * i) for i in range(20)]),
        "ETH": _make_bars("ETH", [50.0 * (1 + 0.01 * i) for i in range(20)]),
    }
    weights = {"BTC": 0.5, "ETH": 0.5}
    m = run_weighted_backtest(prices=prices, weights=weights)
    assert m.curve[-1] > 1.0


def test_run_dynamic_backtest_curve() -> None:
    """动态回测 curve 长度 > 0，首值 == 1.0。"""
    prices = {
        "BTC": _make_bars("BTC", [100.0 + i for i in range(30)]),
        "ETH": _make_bars("ETH", [50.0 + i * 0.5 for i in range(30)]),
    }
    strategy = EqualWeightStrategy()
    (m, _) = run_dynamic_backtest(prices=prices, strategy=strategy, rebalance_days=7)
    assert len(m.curve) > 0
    assert m.curve[0] == 1.0


# ─── Task 3：BacktestResultView + get_backtest_result ────────────────────────

def test_backtest_result_view_has_equity_curve(tmp_path: Path, monkeypatch) -> None:
    """BacktestResultView 应有 equity_curve 字段。"""
    curve = [1.0, 1.05, 1.03, 1.08]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    view = get_backtest_result(rid)
    assert view.equity_curve == json.dumps(curve)


def test_to_dict_includes_equity_curve(tmp_path: Path, monkeypatch) -> None:
    """to_dict() 应包含 equity_curve 键。"""
    curve = [1.0, 1.02, 0.99]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    view = get_backtest_result(rid)
    d = view.to_dict()
    assert "equity_curve" in d
    assert d["equity_curve"] == json.dumps(curve)


def test_get_backtest_result_not_found(tmp_path: Path, monkeypatch) -> None:
    """不存在的 ID 应抛出 ValueError。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    create_all_tables()
    with pytest.raises(ValueError, match="不存在"):
        get_backtest_result(9999)


# ─── Task 4：sparkline + backtest show ────────────────────────────────────────

def test_sparkline_flat() -> None:
    """平坦曲线应全部输出最低字符 ▁。"""
    from hiveflow.cli import _sparkline
    result = _sparkline([1.0, 1.0, 1.0, 1.0, 1.0], width=5)
    assert all(c == "▁" for c in result)


def test_sparkline_rising() -> None:
    """上涨曲线末尾字符不低于首字符。"""
    from hiveflow.cli import _sparkline
    curve = [1.0 + i * 0.01 for i in range(20)]
    result = _sparkline(curve, width=10)
    assert result[-1] >= result[0]


def test_sparkline_width() -> None:
    """输入长度 ≥ width 时，输出恰好 width 个字符。"""
    from hiveflow.cli import _sparkline
    curve = [1.0 + i * 0.01 for i in range(50)]
    result = _sparkline(curve, width=10)
    assert len(result) == 10


def test_backtest_show_cli(tmp_path: Path, monkeypatch) -> None:
    """种入含非空 equity_curve 的回测记录；show 命令应正常输出。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    _SPARK_CHARS = "▁▂▃▄▅▆▇█"
    curve = [1.0 + i * 0.01 for i in range(20)]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0, result.output
    assert "TestStrategy" in result.output
    assert any(c in result.output for c in _SPARK_CHARS)


def test_backtest_show_no_curve(tmp_path: Path, monkeypatch) -> None:
    """equity_curve=NULL 的旧记录应输出降级提示，不报错。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    rid = _seed_record(tmp_path, monkeypatch)  # equity_curve=None
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", str(rid)])
    assert result.exit_code == 0, result.output
    assert "无曲线数据" in result.output


def test_backtest_show_missing_id(tmp_path: Path, monkeypatch) -> None:
    """不存在的 ID 应 exit_code=1，输出含错误提示。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/bt.db")
    from hiveflow.db import create_all_tables
    create_all_tables()
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", "9999"])
    assert result.exit_code == 1
    assert "不存在" in result.output or "错误" in result.output


def test_backtest_show_json_output(tmp_path: Path, monkeypatch) -> None:
    """--output json 应输出可解析的含 strategy_name / equity_curve 键的 dict。"""
    from typer.testing import CliRunner
    from hiveflow.cli import app
    curve = [1.0, 1.02, 1.05]
    rid = _seed_record(tmp_path, monkeypatch, equity_curve=curve)
    runner = CliRunner()
    result = runner.invoke(app, ["backtest", "show", str(rid), "--output", "json"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert "strategy_name" in data
    assert "equity_curve" in data
