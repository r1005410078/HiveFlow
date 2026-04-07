from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from application.market_data.symbol_names import FileSymbolNameLookup
from application.market_data.universe_symbols import list_symbols_from_universe_file


def _default_db_window_dates() -> tuple[str, str]:
    """Last 7 calendar days inclusive (today and 6 days back), Shanghai date."""
    end = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    start = end - timedelta(days=6)
    return start.isoformat(), end.isoformat()


class InstrumentsListService:
    """``GET /instruments``: universe file listing or DB-backed symbol discovery."""

    def __init__(
        self,
        bar_store: Any | None,
        *,
        name_lookup: FileSymbolNameLookup | None = None,
    ):
        self._bar_store = bar_store
        self._names = name_lookup or FileSymbolNameLookup()

    def list_instruments(
        self,
        *,
        mode: str,
        universe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        min_bars: int = 1,
        storage_timeframe: str = "15m",
        limit: int = 100,
        cursor_symbol: str | None = None,
    ) -> dict:
        mode_n = (mode or "").strip().lower()
        if mode_n not in ("universe", "db"):
            raise ValueError("INSTRUMENTS_INVALID_MODE")

        if mode_n == "universe":
            if not universe or not universe.strip():
                raise ValueError("INSTRUMENTS_UNIVERSE_REQUIRED")
            symbols, has_more, next_cursor = self._page_universe(
                universe.strip(),
                after_symbol=cursor_symbol,
                limit=limit,
            )
        else:
            if self._bar_store is None:
                raise ValueError("INSTRUMENTS_DB_UNAVAILABLE")
            if start_date is None and end_date is None:
                start_date, end_date = _default_db_window_dates()
            elif start_date is None or end_date is None:
                raise ValueError("INSTRUMENTS_DATE_WINDOW_INCOMPLETE")
            symbols, has_more = self._bar_store.list_symbols_with_min_bars_in_window(
                storage_timeframe=storage_timeframe,
                start_date=start_date,
                end_date=end_date,
                min_bars=min_bars,
                after_symbol=cursor_symbol,
                limit=limit,
            )
            next_cursor = symbols[-1] if symbols and has_more else None

        snap = self._names.snapshot()
        items = [{"symbol": s, "symbol_name_zh": snap.get(s, "")} for s in symbols]

        return {
            "items": items,
            "has_more": has_more,
            "next_cursor_symbol": next_cursor,
        }

    def _page_universe(
        self,
        universe: str,
        *,
        after_symbol: str | None,
        limit: int,
    ) -> tuple[list[str], bool, str | None]:
        all_syms = list_symbols_from_universe_file(universe)
        if after_symbol:
            page_src = [s for s in all_syms if s > after_symbol]
        else:
            page_src = list(all_syms)
        has_more = len(page_src) > limit
        page = page_src[:limit]
        next_c = page[-1] if page and has_more else None
        return page, has_more, next_c
