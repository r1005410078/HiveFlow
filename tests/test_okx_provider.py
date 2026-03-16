# tests/test_okx_provider.py
import json
from datetime import timezone
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError, OkxProvider, OkxRateLimitError, OkxTimeoutError,
    OkxPosition, OkxCandle, OkxTicker,
)


def _resp(body: dict, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status = status
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


# ── 持仓 ──────────────────────────────────────────────────────────────────────

def test_fetch_positions_returns_spot_balances() -> None:
    """使用 /account/balance，解析 details 列表，包含 USDT，跳过余额为 0 的币种。"""
    payload = {
        "code": "0",
        "data": [{
            "details": [
                {"ccy": "BTC", "availBal": "0.5", "eqUsd": "20000"},
                {"ccy": "ETH", "availBal": "3.0", "eqUsd": "9000"},
                {"ccy": "USDT", "availBal": "100", "eqUsd": "100"},
                {"ccy": "SOL", "availBal": "0", "eqUsd": "0"},        # 余额为0，跳过
            ]
        }],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        p = OkxProvider(api_key="k", api_secret="s", passphrase="p")
        positions = p.fetch_positions()
    assert len(positions) == 3
    symbols = {pos.symbol for pos in positions}
    assert symbols == {"BTC", "ETH", "USDT"}
    btc = next(pos for pos in positions if pos.symbol == "BTC")
    assert btc.quantity == 0.5
    assert btc.market_value_usdt == 20000.0


def test_fetch_positions_raises_on_401() -> None:
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = Exception("HTTP Error 401")
        with pytest.raises(OkxAuthError):
            OkxProvider("k", "s", "p").fetch_positions()


def test_fetch_positions_raises_on_timeout() -> None:
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = TimeoutError()
        with pytest.raises(OkxTimeoutError):
            OkxProvider("k", "s", "p").fetch_positions()


def test_fetch_positions_raises_on_rate_limit_body() -> None:
    """OKX 返回 HTTP 200 但 code=50011 时触发限流异常。"""
    payload = {"code": "50011", "msg": "Too Many Requests", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        with pytest.raises(OkxRateLimitError):
            OkxProvider("k", "s", "p").fetch_positions()


def test_fetch_positions_raises_on_429_http_status() -> None:
    """HTTP 429 状态码触发限流异常（非 code=50011 路径）。"""
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = Exception("HTTP Error 429")
        with pytest.raises(OkxRateLimitError):
            OkxProvider("k", "s", "p").fetch_positions()


# ── 价格（Tickers） ───────────────────────────────────────────────────────────

def test_fetch_tickers_returns_latest_prices() -> None:
    payload = {
        "code": "0",
        "data": [
            {"instId": "BTC-USDT", "last": "70000", "open24h": "68000",
             "high24h": "71000", "low24h": "67000", "vol24h": "500"},
            {"instId": "ETH-USDT", "last": "3000", "open24h": "2900",
             "high24h": "3100", "low24h": "2850", "vol24h": "200"},
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        tickers = OkxProvider("k", "s", "p").fetch_tickers(["BTC-USDT", "ETH-USDT"])
    assert len(tickers) == 2
    assert tickers[0].symbol == "BTC"
    assert tickers[0].last == 70000.0


# ── K 线 ──────────────────────────────────────────────────────────────────────

def test_fetch_candles_returns_daily_bars() -> None:
    payload = {
        "code": "0",
        "data": [
            ["1710288000000", "70000", "71000", "69000", "70500", "100", "100"],
            ["1710201600000", "68000", "70000", "67000", "70000", "90", "90"],
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        candles = OkxProvider("k", "s", "p").fetch_candles("BTC-USDT", days=2)
    assert len(candles) == 2
    assert candles[0].symbol == "BTC"
    assert candles[0].close == 70500.0
    assert candles[0].timestamp.tzinfo is not None
