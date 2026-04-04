"""Read symbol lists from ``quant/config/universes/{universe}.txt`` (server-side)."""

from __future__ import annotations

import re
from pathlib import Path

from application.market_data.symbol_names import resolve_quant_package_root

UNIVERSE_KEYS = ("csi300", "zz500", "all_a", "self_select", "follow")

_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")


def norm_exchange_symbol(symbol: str) -> str:
    """Normalize A-share code; empty input returns empty string (watchlist parsing)."""
    s = symbol.strip().upper()
    if not s:
        return ""
    if not _SYMBOL_PATTERN.match(s):
        raise ValueError(f"invalid symbol format: {symbol}")
    return s


def universe_txt_path(universe: str) -> Path:
    if universe not in UNIVERSE_KEYS:
        raise ValueError(f"unknown universe: {universe}")
    root = resolve_quant_package_root()
    return root / "config" / "universes" / f"{universe}.txt"


def list_symbols_from_universe_file(universe: str) -> list[str]:
    """Return sorted unique symbols from a universe ``.txt`` file (one symbol per line)."""
    if universe not in UNIVERSE_KEYS:
        raise ValueError(f"unknown universe: {universe}")
    path = universe_txt_path(universe)
    if not path.exists():
        raise ValueError(f"unknown universe: {universe}")
    symbols: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        symbols.append(norm_exchange_symbol(line))
    normalized = sorted(set(symbols))
    if not normalized:
        raise ValueError(f"universe {universe} has no symbols")
    return normalized
