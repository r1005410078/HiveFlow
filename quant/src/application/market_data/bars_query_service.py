from __future__ import annotations


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
    ) -> dict:
        items = self.bar_store.list_bars(
            symbols=symbols,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return {"items": items}
