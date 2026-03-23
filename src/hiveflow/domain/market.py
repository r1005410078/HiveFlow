"""市场常量与 symbol 自动检测。"""
from __future__ import annotations

import re

CRYPTO = "crypto"
CN_A_SHARE = "cn_a_share"

ANNUALIZATION_FACTOR: dict[str, int] = {
    CRYPTO: 365,
    CN_A_SHARE: 252,
}

TRADING_DAYS: dict[str, int] = {
    CRYPTO: 365,
    CN_A_SHARE: 252,
}

_CN_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


def detect_market(symbol: str) -> str:
    """根据 symbol 格式自动判断市场。

    000001.SZ / 600000.SH / 830017.BJ → cn_a_share
    其他（BTC、ETH、空字符串、垃圾格式）→ crypto
    """
    cleaned = symbol.strip().upper()
    if _CN_SYMBOL_RE.match(cleaned):
        return CN_A_SHARE
    return CRYPTO
