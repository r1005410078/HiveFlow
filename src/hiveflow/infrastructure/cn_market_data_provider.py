# src/hiveflow/infrastructure/cn_market_data_provider.py
"""A 股行情数据提供者（akshare / tushare 双后端）。"""
from __future__ import annotations

import re
import time
import urllib.request
import warnings
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

    def __init__(
        self,
        source: str,
        token: str = "",
        retry_times: int = 3,
        retry_delay_seconds: float = 0.8,
    ) -> None:
        self._source = source
        self._token = token
        self._retry_times = max(1, retry_times)
        self._retry_delay_seconds = max(0.0, retry_delay_seconds)

    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]:
        if self._source == "akshare":
            return self._fetch_via_akshare(symbols, days)
        elif self._source == "tushare":
            return self._fetch_via_tushare(symbols, days)
        elif self._source == "tencent":
            return self._fetch_via_tencent(symbols, days)
        else:
            raise ValueError(f"不支持的数据源: {self._source!r}，支持 'akshare'、'tushare' 或 'tencent'")

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
            df = self._fetch_akshare_with_retry(
                ak_module=_ak,
                symbol=symbol,
                code=code,
                start_str=start_str,
                end_str=end_str,
            )
            if df is None:
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

    def _fetch_akshare_with_retry(
        self,
        *,
        ak_module,
        symbol: str,
        code: str,
        start_str: str,
        end_str: str,
    ):
        """单个 symbol 的 akshare 拉取重试封装。"""
        last_error: Exception | None = None
        for attempt in range(1, self._retry_times + 1):
            try:
                return ak_module.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",  # 前复权
                )
            except Exception as exc:  # pragma: no cover - 异常类型依赖第三方网络栈
                last_error = exc
                if attempt < self._retry_times:
                    warnings.warn(
                        f"akshare 拉取 {symbol!r} ({code!r}) 失败（第 {attempt}/{self._retry_times} 次）: "
                        f"{type(exc).__name__}: {exc}，准备重试..."
                    )
                    if self._retry_delay_seconds > 0:
                        time.sleep(self._retry_delay_seconds * attempt)
                    continue
                warnings.warn(
                    f"akshare 拉取 {symbol!r} ({code!r}) 失败: {type(exc).__name__}: {exc}"
                )
                return None
        if last_error is not None:
            warnings.warn(
                f"akshare 拉取 {symbol!r} ({code!r}) 失败: {type(last_error).__name__}: {last_error}"
            )
        return None

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
            except Exception as e:
                warnings.warn(f"tushare 拉取 {symbol!r} 失败: {type(e).__name__}: {e}")
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

    # ------------------------------------------------------------------ #
    # tencent 后端（盘中实时快照）
    # ------------------------------------------------------------------ #

    def _to_tencent_code(self, symbol: str) -> str:
        """将 HiveFlow symbol 格式转换为腾讯行情代码。

        000001.SZ → sz000001
        600000.SH → sh600000
        830017.BJ → bj830017
        """
        if "." in symbol:
            code, suffix = symbol.upper().rsplit(".", 1)
            prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "sz")
            return f"{prefix}{code}"
        # 无后缀：首位为 6 → 沪市，否则 → 深市
        return ("sh" if symbol.startswith("6") else "sz") + symbol

    def _fetch_via_tencent(self, symbols: list[str], days: int) -> list[MarketBar]:
        """腾讯行情快照接口（qt.gtimg.cn）。

        注意：只返回当日实时快照（1 bar/symbol），days 参数被忽略。
        适合盘中近实时数据写入，不支持历史数据补齐。
        """
        codes = [self._to_tencent_code(s) for s in symbols]
        url = f"http://qt.gtimg.cn/q={','.join(codes)}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("gbk")
        except Exception as e:
            warnings.warn(f"腾讯行情接口请求失败: {type(e).__name__}: {e}")
            return []

        bars: list[MarketBar] = []
        lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
        for symbol, line in zip(symbols, lines):
            try:
                match = re.search(r'"([^"]+)"', line)
                if not match:
                    continue
                parts = match.group(1).split("~")
                if len(parts) < 35:
                    continue
                # parts[30] = 时间戳，格式 "20260324153000"
                ts_str = parts[30].strip()
                if len(ts_str) >= 14:
                    ts = datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S").replace(
                        tzinfo=timezone.utc
                    )
                else:
                    ts = datetime.now(tz=timezone.utc).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                open_price = float(parts[5]) if parts[5] else float(parts[3])
                bars.append(MarketBar(
                    symbol=symbol.upper(),
                    timestamp=ts,
                    open=open_price,
                    high=float(parts[33]),
                    low=float(parts[34]),
                    close=float(parts[3]),    # 最新价
                    volume=float(parts[6]) * 100,  # 腾讯单位：手（100股）
                    market=CN_A_SHARE,
                ))
            except (IndexError, ValueError) as e:
                warnings.warn(f"腾讯行情解析 {symbol!r} 失败: {e}")
                continue
        return bars
