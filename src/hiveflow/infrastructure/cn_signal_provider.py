# src/hiveflow/infrastructure/cn_signal_provider.py
"""A 股特有信号提供者（腾讯行情主 + akshare 补充/回退）。"""
from __future__ import annotations

import re
import urllib.request
import warnings
from datetime import datetime, timezone

from hiveflow.config import Settings

# 模块级可选导入（支持 patch）
try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]


class CNSignalProvider:
    """A 股特有信号获取器。

    使用 settings.cn_market_data_source 和 settings.tushare_token 配置数据源。
    腾讯行情（qt.gtimg.cn）用于实时涨跌停检测；
    akshare 用于 PE/PB、北向资金、融资余额等深度数据（无腾讯回退）。
    任一数据源失败时对应字段置 None，不中断整体流程。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def fetch_stock_signal(self, symbol: str) -> dict:
        """获取个股信号字段 dict。字段缺失时值为 None。

        返回键：limit_up_hit, limit_down_hit, pe_ratio, pb_ratio, timestamp
        """
        limit_up, limit_down, ts = self._fetch_limit_hit_tencent(symbol)
        if limit_up is None:
            limit_up, limit_down = self._fetch_limit_hit_akshare(symbol)
        pe, pb = self._fetch_pe_pb_akshare(symbol)

        return {
            "limit_up_hit": limit_up,
            "limit_down_hit": limit_down,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "timestamp": ts or datetime.now(tz=timezone.utc),
        }

    def fetch_market_signal(self) -> dict:
        """获取市场级信号字段 dict。字段缺失时值为 None。

        返回键：northbound_net_flow, margin_balance,
                limit_up_count, limit_down_count, timestamp
        """
        northbound = self._fetch_northbound_akshare()
        margin = self._fetch_margin_balance_akshare()
        up_count, down_count = self._fetch_limit_counts_akshare()

        return {
            "northbound_net_flow": northbound,
            "margin_balance": margin,
            "limit_up_count": up_count,
            "limit_down_count": down_count,
            "timestamp": datetime.now(tz=timezone.utc),
        }

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def _to_tencent_code(self, symbol: str) -> str:
        """000001.SZ → sz000001，600000.SH → sh600000，830017.BJ → bj830017。"""
        if "." in symbol:
            code, suffix = symbol.upper().rsplit(".", 1)
            prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "sz")
            return f"{prefix}{code}"
        return ("sh" if symbol.startswith("6") else "sz") + symbol

    def _detect_limit_from_prices(
        self, last: float, prev_close: float
    ) -> tuple[bool, bool]:
        """根据最新价和昨收价判断是否触及涨跌停（主板非 ST ±10%）。"""
        return (last >= prev_close * 1.095, last <= prev_close * 0.905)

    # ------------------------------------------------------------------ #
    # 腾讯后端
    # ------------------------------------------------------------------ #

    def _fetch_limit_hit_tencent(
        self, symbol: str
    ) -> tuple[bool | None, bool | None, datetime | None]:
        """从腾讯行情拉取涨跌停状态。失败时三值均返回 None。"""
        code = self._to_tencent_code(symbol)
        url = f"http://qt.gtimg.cn/q={code}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("gbk")
        except Exception as e:
            warnings.warn(f"腾讯行情拉取 {symbol!r} 失败: {type(e).__name__}: {e}")
            return None, None, None

        try:
            lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
            if not lines:
                return None, None, None
            match = re.search(r'"([^"]+)"', lines[0])
            if not match:
                return None, None, None
            parts = match.group(1).split("~")
            if len(parts) < 35:
                return None, None, None

            last = float(parts[3])
            prev_close = float(parts[4])
            ts_str = parts[30].strip()
            ts = (
                datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if len(ts_str) >= 14
                else datetime.now(tz=timezone.utc)
            )
            limit_up, limit_down = self._detect_limit_from_prices(last, prev_close)
            return limit_up, limit_down, ts
        except (IndexError, ValueError) as e:
            warnings.warn(f"腾讯行情解析 {symbol!r} 失败: {e}")
            return None, None, None

    # ------------------------------------------------------------------ #
    # akshare 后端
    # ------------------------------------------------------------------ #

    def _get_akshare(self):
        """获取模块级 akshare（支持测试 patch）。"""
        import hiveflow.infrastructure.cn_signal_provider as _mod
        _ak = _mod.akshare
        if _ak is None:
            raise ImportError("akshare 未安装。运行: pip install akshare")
        return _ak

    def _fetch_limit_hit_akshare(
        self, symbol: str
    ) -> tuple[bool | None, bool | None]:
        """akshare 回退：当日 K 线推断涨跌停。"""
        try:
            _ak = self._get_akshare()
            code = symbol.split(".")[0] if "." in symbol else symbol
            from datetime import date as _date
            today = _date.today().strftime("%Y%m%d")
            df = _ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=today, end_date=today, adjust="qfq"
            )
            if df is None or df.empty:
                return None, None
            row = df.iloc[-1]
            prev_close = float(row["收盘"]) / (1 + float(row["涨跌幅"]) / 100)
            last = float(row["收盘"])
            return self._detect_limit_from_prices(last, prev_close)
        except Exception as e:
            warnings.warn(f"akshare 回退涨跌停 {symbol!r} 失败: {e}")
            return None, None

    def _fetch_pe_pb_akshare(self, symbol: str) -> tuple[float | None, float | None]:
        """akshare 获取 PE/PB。"""
        try:
            _ak = self._get_akshare()
            code = symbol.split(".")[0] if "." in symbol else symbol
            df = _ak.stock_a_lg_indicator(symbol=code)
            if df is None or df.empty:
                return None, None
            row = df.iloc[-1]
            return float(row["pe"]), float(row["pb"])
        except Exception as e:
            warnings.warn(f"akshare PE/PB {symbol!r} 获取失败: {e}")
            return None, None

    def _fetch_northbound_akshare(self) -> float | None:
        """akshare 获取北向资金净流入（亿元）。"""
        try:
            _ak = self._get_akshare()
            df = _ak.stock_em_hsgt_north_net_flow_in(symbol="沪深港通北向资金")
            if df is None or df.empty:
                return None
            return float(df.iloc[-1]["净买入"])
        except Exception as e:
            warnings.warn(f"akshare 北向资金获取失败: {e}")
            return None

    def _fetch_margin_balance_akshare(self) -> float | None:
        """akshare 获取沪深融资余额合计（亿元）。"""
        try:
            _ak = self._get_akshare()
            sh_df = _ak.stock_em_margin_sh()
            sz_df = _ak.stock_em_margin_sz()
            sh_val = float(sh_df.iloc[-1]["融资余额"]) if sh_df is not None and not sh_df.empty else 0.0
            sz_val = float(sz_df.iloc[-1]["融资余额"]) if sz_df is not None and not sz_df.empty else 0.0
            return sh_val + sz_val
        except Exception as e:
            warnings.warn(f"akshare 融资余额获取失败: {e}")
            return None

    def _fetch_limit_counts_akshare(self) -> tuple[int | None, int | None]:
        """akshare 获取全市场涨停/跌停家数。"""
        try:
            _ak = self._get_akshare()
            df = _ak.stock_limit_up_down_em()
            if df is None or df.empty:
                return None, None
            row = df.iloc[-1]
            return int(row["涨停家数"]), int(row["跌停家数"])
        except Exception as e:
            warnings.warn(f"akshare 涨跌停家数获取失败: {e}")
            return None, None
