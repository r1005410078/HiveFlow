from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from domain.market_data.bars_aggregate import aggregate_storage_rows
from domain.market_data.sse_calendar import is_sse_trading_day

# 聚合前最多拉取的存储粒度行数（避免一次读全表；后续可与游标/分段读结合）
_DEFAULT_STORAGE_FETCH_LIMIT = 10_000


def _parse_bar_time_key(bar_time: str) -> datetime:
    s = bar_time.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        raise ValueError(f"bar_time must be timezone-aware: {bar_time!r}")
    return dt


class BarsQueryService:
    def __init__(self, bar_store):
        self.bar_store = bar_store

    def query(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        session_date: str | None = None,
        cursor_bar_time: str | None = None,
        cursor_symbol: str | None = None,
    ) -> dict:
        output_tf = (timeframe or "1m").strip()

        if output_tf == "1s":
            raise ValueError("TIMEFRAME_FINER_THAN_STORAGE")

        if cursor_bar_time:
            if symbols and len(symbols) > 1:
                raise ValueError("BARS_CURSOR_MULTI_SYMBOL")
            if not symbols or len(symbols) != 1:
                raise ValueError("BARS_CURSOR_SINGLE_SYMBOL_ONLY")
            if cursor_symbol is not None and cursor_symbol != symbols[0]:
                raise ValueError("BARS_CURSOR_SYMBOL_MISMATCH")

        if session_date is not None:
            if not is_sse_trading_day(session_date):
                raise ValueError("SESSION_DATE_NOT_TRADING_DAY")
            start_date = session_date
            end_date = session_date

        raw = self.bar_store.list_storage_bars(
            symbols=symbols,
            storage_timeframe="1m",
            start_date=start_date,
            end_date=end_date,
            limit=_DEFAULT_STORAGE_FETCH_LIMIT,
            order="asc",
        )

        by_sym: dict[str, list[dict]] = defaultdict(list)
        for row in raw:
            sym = row.get("symbol") or ""
            by_sym[sym].append(row)

        items: list[dict] = []
        for sym in sorted(by_sym.keys()):
            sym_rows = sorted(
                by_sym[sym],
                key=lambda r: _parse_bar_time_key(str(r["bar_time"])),
            )
            try:
                part = aggregate_storage_rows(
                    output_tf,
                    sym_rows,
                    session_date=session_date,
                )
            except NotImplementedError as exc:
                raise ValueError("TIMEFRAME_NOT_IMPLEMENTED") from exc
            for it in part:
                it["timeframe"] = output_tf
            items.extend(part)

        intraday_order_asc = session_date is not None
        items.sort(
            key=lambda x: _parse_bar_time_key(str(x["bar_time"])),
            reverse=not intraday_order_asc,
        )

        if cursor_bar_time:
            ctk = _parse_bar_time_key(cursor_bar_time)
            if intraday_order_asc:
                items = [x for x in items if _parse_bar_time_key(str(x["bar_time"])) > ctk]
            else:
                items = [x for x in items if _parse_bar_time_key(str(x["bar_time"])) < ctk]

        lim = limit if limit is not None else 5000
        items = items[:lim]

        return {"items": items}
