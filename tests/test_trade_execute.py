# tests/test_trade_execute.py
import json
from unittest.mock import MagicMock, patch
import pytest
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxOrderResult


def _resp(body: dict) -> MagicMock:
    r = MagicMock()
    r.status = 200
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


def test_place_market_buy_order() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "123456", "clOrdId": "", "sCode": "0", "sMsg": ""}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        provider = OkxProvider("k", "s", "p")
        result = provider.place_market_order(inst_id="BTC-USDT", side="buy", usdt_amount=500.0)
    assert result.order_id == "123456"
    assert result.success is True


def test_place_market_sell_order() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "654321", "clOrdId": "", "sCode": "0", "sMsg": ""}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        provider = OkxProvider("k", "s", "p")
        result = provider.place_market_order(
            inst_id="ETH-USDT", side="sell", usdt_amount=200.0, current_price=3000.0
        )
    assert result.order_id == "654321"
    assert result.success is True


def test_place_order_returns_failure_on_error_code() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "", "clOrdId": "", "sCode": "51008", "sMsg": "Insufficient balance"}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        result = OkxProvider("k", "s", "p").place_market_order(
            inst_id="BTC-USDT", side="buy", usdt_amount=500.0
        )
    assert result.success is False
    assert "Insufficient" in result.error_msg


# 追加到 tests/test_trade_execute.py

import json as _json
from typer.testing import CliRunner
from unittest.mock import patch
from hiveflow.application.trade import TradeOrder, execute_trades
from hiveflow.cli import app
from hiveflow.infrastructure.okx.okx_provider import OkxOrderResult


def _trade_settings(monkeypatch):
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_API_KEY", "tk")
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_API_SECRET", "ts")
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_PASSPHRASE", "tp")


def test_execute_trades_all_success() -> None:
    orders = [
        TradeOrder(symbol="BTC", action="buy", usdt=500.0),
        TradeOrder(symbol="ETH", action="sell", usdt=200.0),
    ]
    mock_result = OkxOrderResult(order_id="123", success=True)
    with patch("hiveflow.application.trade.OkxProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.place_market_order.return_value = mock_result
        instance.fetch_tickers.return_value = []
        results = execute_trades(
            orders=orders,
            api_key="k", api_secret="s", passphrase="p",
        )
    assert all(r.success for r in results)


def test_execute_trades_partial_failure() -> None:
    orders = [
        TradeOrder(symbol="BTC", action="buy", usdt=500.0),
        TradeOrder(symbol="ETH", action="buy", usdt=200.0),
    ]
    def mock_order(inst_id, side, usdt_amount, current_price=None):
        if "BTC" in inst_id:
            return OkxOrderResult(order_id="123", success=True)
        return OkxOrderResult(order_id="", success=False, error_msg="余额不足")

    with patch("hiveflow.application.trade.OkxProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.place_market_order.side_effect = mock_order
        instance.fetch_tickers.return_value = []
        results = execute_trades(
            orders=orders, api_key="k", api_secret="s", passphrase="p",
        )
    assert results[0].success is True
    assert results[1].success is False


def test_trade_execute_cli_no_trade_key() -> None:
    result = CliRunner().invoke(app, [
        "trade", "execute",
        "--orders", '[{"symbol":"BTC","action":"buy","usdt":100}]',
    ])
    assert result.exit_code == 1
    assert "TRADE" in result.output


def test_trade_execute_cli_success(monkeypatch) -> None:
    _trade_settings(monkeypatch)
    with patch("hiveflow.cli.execute_trades", return_value=[
        type("R", (), {"order": TradeOrder(symbol="BTC", action="buy", usdt=100.0),
                       "order_id": "999", "success": True, "error_msg": ""})()
    ]):
        result = CliRunner().invoke(app, [
            "trade", "execute",
            "--orders", '[{"symbol":"BTC","action":"buy","usdt":100}]',
        ], input="confirm\n")
    assert result.exit_code == 0
    assert "999" in result.output
