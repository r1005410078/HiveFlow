"""MA5/MA10 SMA (close) golden/death cross — see spec 2026-04-05-ma-cross-technical-design."""

from __future__ import annotations

# Need at least 11 daily closes: SMA10 at t and t-1 both defined.
_MIN_CLOSES = 11
_SHORT = 5
_LONG = 10


def _sma_window(closes: list[float], end: int, window: int) -> float:
    """Arithmetic mean of closes[end-window : end] (end exclusive)."""
    return sum(closes[end - window : end]) / window


def _cross_state_for_closes(closes: list[float]) -> dict:
    """Single symbol: compute SMA pair at t-1 and t, then cross flags."""
    n = len(closes)
    if n < _MIN_CLOSES:
        return {
            "golden_cross": False,
            "death_cross": False,
            "sma5": None,
            "sma10": None,
            "available": False,
        }
    s5_tm1 = _sma_window(closes, n - 1, _SHORT)
    s10_tm1 = _sma_window(closes, n - 1, _LONG)
    s5_t = _sma_window(closes, n, _SHORT)
    s10_t = _sma_window(closes, n, _LONG)
    golden = s5_tm1 <= s10_tm1 and s5_t > s10_t
    death = s5_tm1 >= s10_tm1 and s5_t < s10_t
    return {
        "golden_cross": golden,
        "death_cross": death,
        "sma5": round(s5_t, 6),
        "sma10": round(s10_t, 6),
        "available": True,
    }


def build_ma_cross_technical(as_of: str, symbols: list[str], bar_rows: list[dict]) -> dict:
    """Build ``technical.ma5_ma10`` payload from flat 1d bar rows (all symbols).

    Bars must be PIT-correct for ``as_of``; rows grouped by ``symbol``, sorted by ``bar_time``.
    """
    by_sym: dict[str, list[dict]] = {}
    for row in bar_rows:
        sym = row.get("symbol")
        if not sym or sym not in symbols:
            continue
        by_sym.setdefault(str(sym), []).append(row)

    by_symbol_out: dict[str, dict] = {}
    for sym in symbols:
        rows = by_sym.get(sym, [])
        ordered = sorted(rows, key=lambda r: str(r.get("bar_time", "")))
        closes: list[float] = []
        for r in ordered:
            try:
                closes.append(float(r["close"]))
            except (KeyError, TypeError, ValueError):
                continue
        by_symbol_out[sym] = _cross_state_for_closes(closes)

    return {
        "schema_version": "1.0.0",
        "definition": "sma_close_5_10",
        "as_of": as_of,
        "by_symbol": by_symbol_out,
    }
