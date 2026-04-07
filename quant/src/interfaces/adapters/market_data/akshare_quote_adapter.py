from __future__ import annotations

from datetime import datetime

from interfaces.adapters.market_data.no_http_proxy_env import disabled_http_proxy_env


class AkshareQuoteAdapter:
    def __init__(self, client=None):
        if client is not None:
            self._ak = client
            return
        try:
            import akshare as ak
        except ImportError as exc:
            raise RuntimeError("akshare is required for real market-data sync") from exc
        self._ak = ak

    @staticmethod
    def _to_ak_symbol(symbol: str) -> str:
        return symbol.split(".", 1)[0]

    @staticmethod
    def _to_iso_8(ts: str) -> str:
        # Keep explicit +08:00 offset for market timestamps.
        return ts.replace(" ", "T") + "+08:00"

    def _fetch_daily(self, symbol: str, as_of: str) -> list[dict]:
        ak_symbol = self._to_ak_symbol(symbol)
        ymd = as_of.replace("-", "")
        df = self._ak.stock_zh_a_hist(
            symbol=ak_symbol,
            period="daily",
            start_date=ymd,
            end_date=ymd,
            adjust="qfq",
        )
        rows: list[dict] = []
        if df is None or df.empty:
            return rows
        for _, row in df.iterrows():
            day = str(row["日期"])
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": "1d",
                    "bar_time": self._to_iso_8(f"{day} 15:00:00"),
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                    "amount": float(row["成交额"]),
                    "adj_factor": 1.0,
                    "data_source": "akshare",
                }
            )
        return rows

    def _fetch_minute(self, symbol: str, as_of: str) -> list[dict]:
        ak_symbol = self._to_ak_symbol(symbol)
        df = self._ak.stock_zh_a_hist_min_em(
            symbol=ak_symbol,
            period="1",
            start_date=f"{as_of} 09:30:00",
            end_date=f"{as_of} 15:00:00",
            adjust="qfq",
        )
        rows: list[dict] = []
        if df is None or df.empty:
            return rows
        for _, row in df.iterrows():
            ts = str(row["时间"])
            # Ensure second precision input to keep stable JSON payload.
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": "1m",
                    "bar_time": self._to_iso_8(ts),
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                    "amount": float(row["成交额"]),
                    "adj_factor": 1.0,
                    "data_source": "akshare",
                }
            )
        return rows

    def _fetch_15m(self, symbol: str, as_of: str) -> list[dict]:
        ak_symbol = self._to_ak_symbol(symbol)
        df = self._ak.stock_zh_a_hist_min_em(
            symbol=ak_symbol,
            period="15",
            start_date=f"{as_of} 09:00:00",
            end_date=f"{as_of} 16:00:00",
            adjust="qfq",
        )
        rows: list[dict] = []
        if df is None or df.empty:
            return rows
        for _, row in df.iterrows():
            ts = str(row["时间"])
            datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": "15m",
                    "bar_time": self._to_iso_8(ts),
                    "open": float(row["开盘"]),
                    "high": float(row["最高"]),
                    "low": float(row["最低"]),
                    "close": float(row["收盘"]),
                    "volume": float(row["成交量"]),
                    "amount": float(row["成交额"]),
                    "adj_factor": 1.0,
                    "data_source": "akshare",
                }
            )
        return rows

    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> list[dict]:
        with disabled_http_proxy_env():
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
