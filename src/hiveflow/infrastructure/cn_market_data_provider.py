# src/hiveflow/infrastructure/cn_market_data_provider.py
"""A 股行情数据提供者（akshare / tushare 双后端）。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from hiveflow.domain.market import CN_A_SHARE
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.providers import MarketDataProvider

# 模块级可选导入：使 akshare / tushare 成为可 patch 的模块属性
try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]

try:
    import tushare  # type: ignore[import]
except ImportError:
    tushare = None  # type: ignore[assignment]


class CNMarketDataProvider(MarketDataProvider):
    """A 股行情提供者，支持 akshare 和 tushare 两个后端，通过 source 参数切换。"""

    def __init__(self, source: str, token: str = "") -> None:
        self._source = source
        self._token = token

    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]:
        if self._source == "akshare":
            return self._fetch_via_akshare(symbols, days)
        elif self._source == "tushare":
            return self._fetch_via_tushare(symbols, days)
        else:
            raise ValueError(f"不支持的数据源: {self._source!r}，支持 'akshare' 或 'tushare'")

    # ------------------------------------------------------------------ #
    # akshare 后端
    # ------------------------------------------------------------------ #

    def _fetch_via_akshare(self, symbols: list[str], days: int) -> list[MarketBar]:
        # 使用模块级 akshare 变量（支持 patch）
        import hiveflow.infrastructure.cn_market_data_provider as _self_mod
        _ak = _self_mod.akshare
        if _ak is None:
            raise ImportError(
                "akshare 未安装。请运行: uv pip install 'hiveflow[cn]' 或 pip install akshare"
            )
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=days)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        bars: list[MarketBar] = []
        for symbol in symbols:
            # akshare 期望 6 位代码（无交易所后缀）
            code = symbol.split(".")[0] if "." in symbol else symbol
            try:
                df = _ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",  # 前复权
                )
            except Exception:
                continue  # 单个 symbol 失败不中断整批

            for _, row in df.iterrows():
                try:
                    ts = datetime.strptime(str(row["日期"]), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    bars.append(MarketBar(
                        symbol=symbol.upper(),
                        timestamp=ts,
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row["成交量"]),
                        market=CN_A_SHARE,
                    ))
                except (KeyError, ValueError):
                    continue
        return bars

    # ------------------------------------------------------------------ #
    # tushare 后端
    # ------------------------------------------------------------------ #

    def _fetch_via_tushare(self, symbols: list[str], days: int) -> list[MarketBar]:
        # 使用模块级 tushare 变量（支持 patch）
        import hiveflow.infrastructure.cn_market_data_provider as _self_mod
        _ts = _self_mod.tushare
        if _ts is None:
            raise ImportError(
                "tushare 未安装。请运行: uv pip install 'hiveflow[cn]' 或 pip install tushare"
            )
        pro = _ts.pro_api(self._token)
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=days)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        bars: list[MarketBar] = []
        for symbol in symbols:
            ts_code = symbol.upper()
            try:
                df = pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
            except Exception:
                continue

            for _, row in df.iterrows():
                try:
                    ts_date = str(row["trade_date"])
                    ts_dt = datetime.strptime(ts_date, "%Y%m%d").replace(
                        tzinfo=timezone.utc
                    )
                    bars.append(MarketBar(
                        symbol=symbol.upper(),
                        timestamp=ts_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["vol"]),
                        market=CN_A_SHARE,
                    ))
                except (KeyError, ValueError):
                    continue
        return bars
