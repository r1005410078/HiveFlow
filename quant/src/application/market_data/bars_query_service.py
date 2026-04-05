from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

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
        has_more = len(items) > lim
        page = items[:lim]

        next_bt: str | None = None
        next_sym: str | None = None
        if (
            has_more
            and page
            and symbols
            and len(symbols) == 1
        ):
            next_bt = str(page[-1]["bar_time"])
            next_sym = symbols[0]

        return {
            "items": page,
            "next_cursor_bar_time": next_bt,
            "next_cursor_symbol": next_sym,
        }

    def query_bundle(
        self,
        symbols: list[str],
        timeframes: list[str],
        start_date: str | None = None,
        end_date: str | None = None,
        limit_per_timeframe: int | None = None,
    ) -> dict:
        """一次读存储 1m 行，再对每个 timeframe 分别聚合（无 session_date / 游标）。"""
        if not symbols:
            raise ValueError("BARS_BUNDLE_SYMBOLS_REQUIRED")
        if not timeframes:
            raise ValueError("BARS_BUNDLE_TIMEFRAMES_REQUIRED")

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

        lim = limit_per_timeframe if limit_per_timeframe is not None else 5000
        by_tf: dict[str, dict] = {}

        for tf_raw in timeframes:
            output_tf = (tf_raw or "").strip()
            if output_tf == "1s":
                raise ValueError("TIMEFRAME_FINER_THAN_STORAGE")

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
                        session_date=None,
                    )
                except NotImplementedError as exc:
                    raise ValueError("TIMEFRAME_NOT_IMPLEMENTED") from exc
                for it in part:
                    it["timeframe"] = output_tf
                items.extend(part)

            items.sort(
                key=lambda x: _parse_bar_time_key(str(x["bar_time"])),
                reverse=True,
            )
            has_more = len(items) > lim
            by_tf[output_tf] = {
                "items": items[:lim],
                "has_more": has_more,
            }

        return {
            "schema_version": "1.0.0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "producer_version": "hiveflow-quant-bars-bundle-1.0.0",
            "by_timeframe": by_tf,
        }
