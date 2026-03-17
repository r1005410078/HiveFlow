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


@dataclass(frozen=True)
class OkxGridPosition:
    symbol: str
    grid_id: str
    inst_id: str
    base_quantity: float
    quote_quantity: float
    state: str
    inst_type: str = "SPOT"


@dataclass(frozen=True)
class OkxOrderResult:
    order_id: str
    success: bool
    error_msg: str = ""


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
            if not symbol:
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

    def fetch_grid_positions(self) -> list[OkxGridPosition]:
        """拉取所有网格机器人持仓（现货 + 合约）。

        先用 orders-algo-pending 获取运行中的网格机器人列表，
        再逐个调用 grid/positions?algoId=xxx 获取持仓数量。
        """
        result: list[OkxGridPosition] = []
        for inst_type, algo_ord_type in [("SPOT", "grid"), ("SWAP", "contract_grid")]:
            result.extend(self._fetch_grid_by_type(inst_type, algo_ord_type))
        return result

    def _fetch_grid_by_type(self, inst_type: str, algo_ord_type: str) -> list[OkxGridPosition]:
        try:
            algos = self._get_auth(
                f"/api/v5/tradingBot/grid/orders-algo-pending"
                f"?instType={inst_type}&algoOrdType={algo_ord_type}"
            )
        except (OkxAuthError, OkxTimeoutError):
            return []

        result = []
        for algo in algos:
            algo_id = str(algo.get("algoId", ""))
            inst_id = algo.get("instId", "")
            if not algo_id or not inst_id:
                continue
            symbol = inst_id.split("-")[0].upper()
            try:
                positions = self._get_auth(
                    f"/api/v5/tradingBot/grid/positions?algoId={algo_id}&instType={inst_type}"
                )
            except (OkxAuthError, OkxTimeoutError):
                positions = []
            if inst_type == "SPOT":
                # 现货网格：baseSz=基础资产数量，quoteSz=USDT数量
                if positions:
                    p = positions[0]
                    base_qty = float(p.get("baseSz") or algo.get("baseSz") or 0)
                    quote_qty = float(p.get("quoteSz") or algo.get("quoteSz") or 0)
                else:
                    base_qty = float(algo.get("baseSz") or 0)
                    quote_qty = float(algo.get("quoteSz") or 0)
            else:
                # 合约网格：baseSz/quoteSz 为空，投入资金在 investment（同 sz）
                base_qty = 0.0
                quote_qty = float(algo.get("investment") or algo.get("sz") or 0)
            result.append(OkxGridPosition(
                symbol=symbol,
                grid_id=algo_id,
                inst_id=inst_id,
                base_quantity=base_qty,
                quote_quantity=quote_qty,
                state=str(algo.get("state", "running")),
                inst_type=inst_type,
            ))
        return result

    def place_market_order(
        self,
        inst_id: str,
        side: str,
        usdt_amount: float,
        current_price: float | None = None,
    ) -> OkxOrderResult:
        """下现货市价单。
        side='buy': sz 以 USDT 计（tgtCcy=quote_ccy）。
        side='sell': sz 以基础资产计，需传入 current_price 换算。
        """
        if side == "buy":
            sz = str(round(usdt_amount, 2))
            body: dict = {
                "instId": inst_id,
                "tdMode": "cash",
                "side": "buy",
                "ordType": "market",
                "sz": sz,
                "tgtCcy": "quote_ccy",
            }
        else:
            if current_price is None or current_price <= 0:
                return OkxOrderResult(order_id="", success=False,
                                      error_msg="卖单需要提供 current_price")
            base_sz = round(usdt_amount / current_price, 8)
            body = {
                "instId": inst_id,
                "tdMode": "cash",
                "side": "sell",
                "ordType": "market",
                "sz": str(base_sz),
            }
        data = self._post_auth("/api/v5/trade/order", body)
        if not data:
            return OkxOrderResult(order_id="", success=False, error_msg="空响应")
        item = data[0]
        s_code = str(item.get("sCode", "0"))
        if s_code != "0":
            return OkxOrderResult(order_id="", success=False,
                                   error_msg=item.get("sMsg", "未知错误"))
        return OkxOrderResult(order_id=str(item.get("ordId", "")), success=True)

    # ── 私有工具 ──────────────────────────────────────────────────────────────

    def _post_auth(self, path: str, body: dict) -> list:
        ts = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        body_str = json.dumps(body)
        sign = self._sign("POST", path, ts, body_str)
        req = urllib.request.Request(
            BASE_URL + path,
            data=body_str.encode(),
            headers={
                "OK-ACCESS-KEY": self._key,
                "OK-ACCESS-SIGN": sign,
                "OK-ACCESS-TIMESTAMP": ts,
                "OK-ACCESS-PASSPHRASE": self._pass,
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                resp_body = json.loads(resp.read())
        except TimeoutError:
            raise OkxTimeoutError("网络超时，请稍后重试。")
        except Exception as e:
            msg = str(e)
            if "401" in msg:
                raise OkxAuthError("OKX Trade API 鉴权失败（401）。")
            raise OkxTimeoutError(f"网络请求失败：{msg}")
        code = resp_body.get("code", "0")
        if code != "0":
            raise OkxAuthError(f"OKX API 错误 code={code}：{resp_body.get('msg')}")
        return resp_body.get("data", [])

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
            if "400" in msg:
                raise OkxAuthError(
                    f"OKX API 请求无效（400）。可能原因：接口不支持、缺少权限或参数错误。路径：{path}"
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
            if "400" in msg:
                raise OkxAuthError(
                    f"OKX API 请求无效（400）。可能原因：接口不支持、缺少权限或参数错误。路径：{path}"
                )
            raise OkxTimeoutError(f"网络请求失败：{msg}")

        code = body.get("code", "0")
        if code == "50011":
            raise OkxRateLimitError("请求频率超限（50011），请稍后重试。")
        if code != "0":
            raise OkxAuthError(f"OKX API 错误 code={code}：{body.get('msg')}")
        return body.get("data", [])
