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
