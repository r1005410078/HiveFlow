# src/hiveflow/infrastructure/okx/okx_provider.py
"""OKX REST API 客户端——纯 HTTP 数据拉取，无业务逻辑。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

BASE_URL = "https://www.okx.com"
TIMEOUT = 10
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)


class OkxAuthError(Exception): ...
class OkxTimeoutError(Exception): ...
class OkxRateLimitError(Exception): ...


@dataclass(frozen=True)
class OkxPosition:
    symbol: str
    quantity: float
    market_value_usdt: float


@dataclass(frozen=True)
class OkxTicker:
    symbol: str
    last: float
    open24h: float
    high24h: float
    low24h: float
    vol24h: float


@dataclass(frozen=True)
class OkxCandle:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OkxProvider:
    def __init__(self, api_key: str, api_secret: str, passphrase: str) -> None:
        self._key = api_key
        self._secret = api_secret
        self._pass = passphrase

    def fetch_positions(self) -> list[OkxPosition]:
        """拉取现货余额（GET /api/v5/account/balance），仅需 Read 权限。"""
        data = self._get_auth("/api/v5/account/balance")
        result = []
        # 响应结构：data[0].details[] 包含各币种余额
        details = data[0].get("details", []) if data else []
        for item in details:
            symbol = item.get("ccy", "").upper()
            if not symbol or symbol == "USDT":
                continue
            qty = float(item.get("availBal") or 0)
            val = float(item.get("eqUsd") or 0)
            if qty <= 0:
                continue
            result.append(OkxPosition(symbol=symbol, quantity=qty, market_value_usdt=val))
        return result

    def fetch_tickers(self, inst_ids: list[str]) -> list[OkxTicker]:
        """拉取现货当前行情（GET /api/v5/market/ticker，逐个请求）。"""
        tickers = []
        for inst_id in inst_ids:
            data = self._get_public(f"/api/v5/market/ticker?instId={inst_id}")
            if not data:
                continue
            item = data[0]
            symbol = inst_id.split("-")[0].upper()
            tickers.append(OkxTicker(
                symbol=symbol,
                last=float(item.get("last") or 0),
                open24h=float(item.get("open24h") or 0),
                high24h=float(item.get("high24h") or 0),
                low24h=float(item.get("low24h") or 0),
                vol24h=float(item.get("vol24h") or 0),
            ))
        return tickers

    def fetch_candles(self, inst_id: str, days: int) -> list[OkxCandle]:
        """拉取日线 K 线，days 最大 100（OKX 单次限制）。"""
        symbol = inst_id.split("-")[0].upper()
        limit = min(days, 100)
        path = f"/api/v5/market/candles?instId={inst_id}&bar=1D&limit={limit}"
        data = self._get_public(path)
        candles = []
        for row in data:
            ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
            candles.append(OkxCandle(
                symbol=symbol, timestamp=ts,
                open=float(row[1]), high=float(row[2]),
                low=float(row[3]), close=float(row[4]), volume=float(row[5]),
            ))
        return candles

    # ── 私有工具 ──────────────────────────────────────────────────────────────

    def _get_auth(self, path: str) -> list:
        ts = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        sign = self._sign("GET", path, ts, "")
        headers = {
            "OK-ACCESS-KEY": self._key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._pass,
        }
        return self._request(path, headers)

    def _get_public(self, path: str) -> list:
        return self._request(path, {})

    def _sign(self, method: str, path: str, ts: str, body: str) -> str:
        msg = f"{ts}{method}{path}{body}"
        mac = hmac.new(self._secret.encode(), msg.encode(), hashlib.sha256)
        return base64.b64encode(mac.digest()).decode()

    def _request(self, path: str, headers: dict) -> list:
        base_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        base_headers.update(headers)
        req = urllib.request.Request(BASE_URL + path, headers=base_headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = json.loads(resp.read())
        except (TimeoutError, urllib.error.URLError) as e:
            # urllib wraps socket.timeout in URLError; bare TimeoutError for test mocks
            if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
                raise OkxTimeoutError("网络超时，请稍后重试。")
            msg = str(e)
            if "429" in msg:
                raise OkxRateLimitError("请求频率超限，请稍后重试。")
            if "403" in msg:
                raise OkxAuthError(
                    "OKX API 访问被拒绝（403）。请检查：\n"
                    "  1. OKX API Key 是否已开启读取权限\n"
                    "  2. OKX API Key 是否绑定了 IP 白名单（如有，需添加你的出口 IP）"
                )
            if "401" in msg:
                raise OkxAuthError(
                    "OKX API 鉴权失败（401）。请检查 .env 中的 HIVEFLOW_OKX_API_KEY / _SECRET / _PASSPHRASE。"
                )
            raise OkxTimeoutError(f"网络请求失败：{msg}")
        except Exception as e:
            msg = str(e)
            if "429" in msg:
                raise OkxRateLimitError("请求频率超限，请稍后重试。")
            if "403" in msg:
                raise OkxAuthError(
                    "OKX API 访问被拒绝（403）。请检查：\n"
                    "  1. OKX API Key 是否已开启读取权限\n"
                    "  2. OKX API Key 是否绑定了 IP 白名单（如有，需添加你的出口 IP）"
                )
            if "401" in msg:
                raise OkxAuthError(
                    "OKX API 鉴权失败（401）。请检查 .env 中的 HIVEFLOW_OKX_API_KEY / _SECRET / _PASSPHRASE。"
                )
            raise OkxTimeoutError(f"网络请求失败：{msg}")

        code = body.get("code", "0")
        if code == "50011":
            raise OkxRateLimitError("请求频率超限（50011），请稍后重试。")
        if code != "0":
            raise OkxAuthError(f"OKX API 错误 code={code}：{body.get('msg')}")
        return body.get("data", [])
