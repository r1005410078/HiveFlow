from __future__ import annotations

import json
from datetime import datetime
import urllib.parse
import urllib.request


class TencentQuoteAdapter:
    """Tencent 行情适配器（优先数据源）。"""

    def __init__(self, http_get=None):
        self._http_get = http_get or self._default_http_get

    @staticmethod
    def _default_http_get(url: str) -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=10) as resp:
            return resp.read().decode("utf-8", errors="ignore")

    @staticmethod
    def _to_tencent_code(symbol: str) -> str:
        code, suffix = symbol.upper().split(".", 1)
        prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix)
        if not prefix:
            raise ValueError(f"unsupported symbol suffix: {symbol}")
        return f"{prefix}{code}"

    @staticmethod
    def _to_iso_8(ts: str) -> str:
        return ts.replace(" ", "T") + "+08:00"

    @staticmethod
    def _to_iso_8_minute(ts: str) -> str:
        text = str(ts).strip()
        if len(text) == 12 and text.isdigit():
            # 202604010931 -> 2026-04-01T09:31:00+08:00
            dt = datetime.strptime(text, "%Y%m%d%H%M")
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        if len(text) == 14 and text.isdigit():
            # 20260401093145 -> 2026-04-01T09:31:45+08:00
            dt = datetime.strptime(text, "%Y%m%d%H%M%S")
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        if len(text) == 16:
            # 2026-04-01 09:31
            dt = datetime.strptime(text, "%Y-%m-%d %H:%M")
            return dt.strftime("%Y-%m-%dT%H:%M:%S+08:00")
        # Fallback to original behavior for already expanded format.
        return TencentQuoteAdapter._to_iso_8(text)

    @staticmethod
    def _to_float(value, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _fetch_daily(self, symbol: str, as_of: str) -> list[dict]:
        code = self._to_tencent_code(symbol)
        params = urllib.parse.quote(f"{code},day,{as_of},{as_of},1,qfq")
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={params}"
        raw = self._http_get(url)
        payload = json.loads(raw)
        arr = (((payload.get("data") or {}).get(code) or {}).get("qfqday")) or []
        rows: list[dict] = []
        for item in arr:
            if not isinstance(item, (list, tuple)):
                continue
            if len(item) < 6:
                continue
            day, open_p, close_p, high_p, low_p, vol_p = item[:6]
            amount_p = item[6] if len(item) > 6 else 0
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": "1d",
                    "bar_time": self._to_iso_8(f"{day} 15:00:00"),
                    "open": float(open_p),
                    "high": float(high_p),
                    "low": float(low_p),
                    "close": float(close_p),
                    "volume": float(vol_p),
                    "amount": float(amount_p),
                    "adj_factor": 1.0,
                    "data_source": "tencent",
                }
            )
        return rows

    @staticmethod
    def _mkline_amount_volume(item: list | tuple) -> tuple[float, float]:
        vol = TencentQuoteAdapter._to_float(item[5] if len(item) > 5 else 0)
        if len(item) > 7:
            return vol, TencentQuoteAdapter._to_float(item[7])
        if len(item) > 6 and not isinstance(item[6], dict):
            return vol, TencentQuoteAdapter._to_float(item[6])
        return vol, 0.0

    def _fetch_mkline(
        self,
        symbol: str,
        as_of: str,
        *,
        mk_key: str,
        bar_timeframe: str,
        max_points: int,
    ) -> list[dict]:
        code = self._to_tencent_code(symbol)
        # Latest-chunk endpoint; filter bars to the requested calendar session day.
        params = urllib.parse.quote(f"{code},{mk_key},,{max_points}")
        url = f"https://ifzq.gtimg.cn/appstock/app/kline/mkline?param={params}"
        raw = self._http_get(url)
        payload = json.loads(raw)
        arr = (((payload.get("data") or {}).get(code) or {}).get(mk_key)) or []
        rows: list[dict] = []
        for item in arr:
            if not isinstance(item, (list, tuple)):
                continue
            if len(item) < 6:
                continue
            ts, open_p, close_p, high_p, low_p, _vol = item[:6]
            iso_ts = self._to_iso_8_minute(str(ts))
            if not iso_ts.startswith(f"{as_of}T"):
                continue
            vol_p, amount_p = self._mkline_amount_volume(item)
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": bar_timeframe,
                    "bar_time": iso_ts,
                    "open": self._to_float(open_p),
                    "high": self._to_float(high_p),
                    "low": self._to_float(low_p),
                    "close": self._to_float(close_p),
                    "volume": vol_p,
                    "amount": amount_p,
                    "adj_factor": 1.0,
                    "data_source": "tencent",
                }
            )
        return rows

    def _fetch_minute(self, symbol: str, as_of: str) -> list[dict]:
        return self._fetch_mkline(symbol, as_of, mk_key="m1", bar_timeframe="1m", max_points=480)

    def _fetch_15m(self, symbol: str, as_of: str) -> list[dict]:
        return self._fetch_mkline(symbol, as_of, mk_key="m15", bar_timeframe="15m", max_points=320)

    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> list[dict]:
        rows: list[dict] = []
        for symbol in symbols:
            if timeframe == "1d":
                rows.extend(self._fetch_daily(symbol=symbol, as_of=as_of))
            elif timeframe == "1m":
                rows.extend(self._fetch_minute(symbol=symbol, as_of=as_of))
            elif timeframe == "15m":
                rows.extend(self._fetch_15m(symbol=symbol, as_of=as_of))
            else:
                raise ValueError(f"unsupported timeframe: {timeframe}")
        return rows
