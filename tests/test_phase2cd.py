"""Phase 2-C/D 测试：OKX 接口化 + 跨市场货币折算。"""
from __future__ import annotations

import json
import sqlite3
import warnings
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position
from hiveflow.domain.providers import PositionProvider
from hiveflow.infrastructure.okx.okx_provider import OkxProvider


def test_position_has_currency_field() -> None:
    """Position 实体应有 currency 字段，默认值 'USDT'。"""
    p = Position(symbol="BTC", quantity=0.1, market_value=1000.0, weight=0.5)
    assert p.currency == "USDT"


def test_position_currency_can_be_cny() -> None:
    """Position currency 可以设置为 'CNY'。"""
    p = Position(
        symbol="000001.SZ",
        quantity=100.0,
        market_value=1000.0,
        weight=0.1,
        market="cn_a_share",
        currency="CNY",
    )
    assert p.currency == "CNY"


def test_migration_adds_currency_column_with_default(tmp_path) -> None:
    """旧数据库（无 currency 列）迁移后，已有行的 currency == 'USDT'。"""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE position (id INTEGER PRIMARY KEY, symbol TEXT, "
        "quantity REAL DEFAULT 0, market_value REAL DEFAULT 0, "
        "weight REAL DEFAULT 0, updated_at TEXT, market TEXT DEFAULT 'crypto')"
    )
    conn.execute(
        "INSERT INTO position (symbol, quantity, market_value, weight) "
        "VALUES ('BTC', 0.1, 1000.0, 0.5)"
    )
    conn.commit()
    conn.close()

    settings = Settings(database_url=f"sqlite:///{db_path}")
    create_all_tables(settings)

    conn2 = sqlite3.connect(str(db_path))
    row = conn2.execute("SELECT currency FROM position WHERE symbol='BTC'").fetchone()
    conn2.close()
    assert row is not None
    assert row[0] == "USDT"


# ---- FxRateProvider ----
import hiveflow.infrastructure.fx_rate_provider as _fx_mod  # noqa: E402


def test_fx_rate_provider_akshare_success() -> None:
    """akshare 正常返回时，get_cny_per_usdt 返回 (rate, 'akshare')。"""
    import pandas as pd

    mock_df = pd.DataFrame({"中行折算价": ["7.28", "7.30"]})
    mock_ak = MagicMock()
    mock_ak.currency_boc_sina.return_value = mock_df
    original = _fx_mod.akshare
    _fx_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.fx_rate_provider import FxRateProvider

        provider = FxRateProvider(Settings(cny_usdt_rate=7.25))
        rate, source = provider.get_cny_per_usdt()
    finally:
        _fx_mod.akshare = original
    assert rate == 7.30
    assert source == "akshare"


def test_fx_rate_provider_akshare_failure_fallback() -> None:
    """akshare 失败时返回 config 回退值，不抛异常，发出 warning。"""
    mock_ak = MagicMock()
    mock_ak.currency_boc_sina.side_effect = Exception("network error")
    original = _fx_mod.akshare
    _fx_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.fx_rate_provider import FxRateProvider

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            provider = FxRateProvider(Settings(cny_usdt_rate=7.25))
            rate, source = provider.get_cny_per_usdt()
    finally:
        _fx_mod.akshare = original
    assert rate == 7.25
    assert source == "config_fallback"
    assert len(w) >= 1


def _okx_resp(body: dict) -> MagicMock:
    r = MagicMock()
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


def test_okx_provider_implements_position_provider() -> None:
    provider = OkxProvider(api_key="k", api_secret="s", passphrase="p")
    assert isinstance(provider, PositionProvider)


def test_okx_provider_fetch_positions_currency_usdt() -> None:
    payload = {
        "code": "0",
        "data": [
            {
                "details": [
                    {"ccy": "BTC", "availBal": "0.5", "eqUsd": "20000"},
                    {"ccy": "USDT", "availBal": "100", "eqUsd": "100"},
                ]
            }
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _okx_resp(payload)
        rows = OkxProvider("k", "s", "p").fetch_positions()
    assert rows
    assert all(isinstance(p, Position) for p in rows)
    assert all(p.currency == "USDT" for p in rows)
    assert all(p.market == "crypto" for p in rows)


def test_build_portfolio_summary_mixed_currencies(tmp_path) -> None:
    from hiveflow.application.portfolio import build_portfolio_summary

    settings = Settings(database_url=f"sqlite:///{tmp_path}/mix.db")
    create_all_tables(settings)
    with get_session(settings) as session:
        session.add(
            Position(
                symbol="BTC",
                quantity=0.1,
                market_value=10000,
                weight=0.0,
                market="crypto",
                currency="USDT",
            )
        )
        session.add(
            Position(
                symbol="000001.SZ",
                quantity=1000,
                market_value=14000,
                weight=0.0,
                market="cn_a_share",
                currency="CNY",
            )
        )
        session.commit()

    with patch(
        "hiveflow.application.portfolio.FxRateProvider.get_cny_per_usdt",
        return_value=(7.0, "akshare"),
    ):
        summary = build_portfolio_summary(settings)

    assert summary.fx_rate == 7.0
    assert summary.fx_source == "akshare"
    assert summary.total_usdt == pytest.approx(12000.0)
    assert summary.total_cny == pytest.approx(84000.0)
    assert summary.breakdown["crypto"]["currency"] == "USDT"
    assert summary.breakdown["cn_a_share"]["currency"] == "CNY"
    assert summary.breakdown["crypto"]["weight"] + summary.breakdown["cn_a_share"]["weight"] == pytest.approx(1.0)


def test_build_portfolio_summary_empty(tmp_path) -> None:
    from hiveflow.application.portfolio import build_portfolio_summary

    settings = Settings(database_url=f"sqlite:///{tmp_path}/empty.db")
    create_all_tables(settings)
    with patch(
        "hiveflow.application.portfolio.FxRateProvider.get_cny_per_usdt",
        return_value=(7.2, "config_fallback"),
    ):
        summary = build_portfolio_summary(settings)

    assert summary.positions == []
    assert summary.total_usdt == 0.0
    assert summary.total_cny == 0.0
    assert summary.breakdown == {}


def test_cli_portfolio_summary_text(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "portfolio-cli.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables(Settings(database_url=f"sqlite:///{db_path}"))
    with get_session(Settings(database_url=f"sqlite:///{db_path}")) as session:
        session.add(Position(symbol="BTC", quantity=0.1, market_value=10000, weight=0.5, market="crypto", currency="USDT"))
        session.add(Position(symbol="000001.SZ", quantity=1000, market_value=14000, weight=0.5, market="cn_a_share", currency="CNY"))
        session.commit()

    with patch(
        "hiveflow.application.portfolio.FxRateProvider.get_cny_per_usdt",
        return_value=(7.0, "akshare"),
    ):
        result = CliRunner().invoke(app, ["portfolio", "summary"])
    assert result.exit_code == 0
    assert "总资产（USDT）" in result.output
    assert "总资产（CNY）" in result.output
    assert "汇率" in result.output


def test_cli_portfolio_summary_json(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "portfolio-cli-json.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables(Settings(database_url=f"sqlite:///{db_path}"))
    with get_session(Settings(database_url=f"sqlite:///{db_path}")) as session:
        session.add(Position(symbol="BTC", quantity=0.1, market_value=10000, weight=1.0, market="crypto", currency="USDT"))
        session.commit()

    with patch(
        "hiveflow.application.portfolio.FxRateProvider.get_cny_per_usdt",
        return_value=(7.2, "config_fallback"),
    ):
        result = CliRunner().invoke(app, ["portfolio", "summary", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["fx_rate"] == 7.2
    assert payload["fx_source"] == "config_fallback"
    assert "breakdown" in payload
    assert "positions" in payload


def test_cli_positions_list_fx_columns(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "positions-fx.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables(Settings(database_url=f"sqlite:///{db_path}"))
    with get_session(Settings(database_url=f"sqlite:///{db_path}")) as session:
        session.add(Position(symbol="BTC", quantity=0.1, market_value=10000, weight=1.0, market="crypto", currency="USDT"))
        session.commit()

    with patch(
        "hiveflow.application.portfolio.FxRateProvider.get_cny_per_usdt",
        return_value=(7.2, "config_fallback"),
    ):
        result = CliRunner().invoke(app, ["positions", "list"])

    assert result.exit_code == 0
    assert "市值(USDT)" in result.output
    assert "市值(CNY)" in result.output
    assert "占比（全局）" in result.output
