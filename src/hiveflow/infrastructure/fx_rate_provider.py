"""汇率提供者：akshare 主 + Settings 回退。"""
from __future__ import annotations

import io
import warnings
from contextlib import redirect_stderr, redirect_stdout

from hiveflow.config import Settings

try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]


class FxRateProvider:
    """获取 CNY/USDT 汇率。"""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def get_cny_per_usdt(self) -> tuple[float, str]:
        """返回 (汇率, 来源)。汇率定义：1 USDT ≈ ? CNY。"""
        import hiveflow.infrastructure.fx_rate_provider as _self_mod

        _ak = _self_mod.akshare
        if _ak is not None:
            try:
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    df = _ak.currency_boc_sina(symbol="美元")
                if df is not None and not df.empty and "中行折算价" in df.columns:
                    rate = float(df.iloc[-1]["中行折算价"])
                    if 1.0 <= rate <= 20.0:
                        return rate, "akshare"
            except Exception as e:
                warnings.warn(
                    f"FxRateProvider akshare 获取汇率失败: {e}，使用配置回退值",
                    stacklevel=2,
                )
        return float(self._settings.cny_usdt_rate), "config_fallback"
