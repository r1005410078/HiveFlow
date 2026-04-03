"""DataFrame 辅助：与 ``application.factor.basic_factor_service`` 共用同一套因子公式。

生产日频路径使用 ``compute_basic_factor_snapshot_from_bars``；本模块仅保留窄用例
（测试、notebook）需要的逐行因果因子序列，避免与 L2 主实现分叉。
"""

from __future__ import annotations

import pandas as pd

from application.factor.basic_factor_service import (
    FACTOR_METADATA,
    compute_raw_factor_values_from_bar_rows,
)


def compute_basic_factors(df: pd.DataFrame) -> pd.DataFrame:
    """按行追加 L2 因子列，与 :func:`compute_raw_factor_values_from_bar_rows` 公式一致。

    对第 ``i`` 行（``i >= 60``），使用 ``0..i``（含）的 bars 计算因子，即仅使用当期及历史数据。
    更早行为 NaN。若 ``volume`` 缺失则使用 ``turnover`` 作为成交量代理（兼容旧测试）。
    """
    if "close" not in df.columns:
        raise ValueError("compute_basic_factors requires a 'close' column")

    out = df.copy()
    vol = (
        df["volume"].astype(float)
        if "volume" in df.columns
        else df["turnover"].astype(float)
        if "turnover" in df.columns
        else pd.Series([0.0] * len(df), dtype=float)
    )

    closes = df["close"].astype(float)
    n = len(df)
    bars = [
        {
            "symbol": "_frame",
            "bar_time": f"{i:06d}",
            "close": float(closes.iloc[i]),
            "volume": float(vol.iloc[i]),
        }
        for i in range(n)
    ]

    for name in FACTOR_METADATA:
        out[name] = [float("nan")] * n

    # 首根可用完整 61-bar 窗口的行为索引 60
    for i in range(60, n):
        vals = compute_raw_factor_values_from_bar_rows(bars[: i + 1])
        if vals:
            idx = out.index[i]
            for name in FACTOR_METADATA:
                out.at[idx, name] = vals[name]

    return out
