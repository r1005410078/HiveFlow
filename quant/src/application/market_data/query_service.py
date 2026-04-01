from __future__ import annotations


class QueryService:
    def __init__(self, bar_store):
        self.bar_store = bar_store

    def query(
        self,
        days: int,
        timeframe: str | None = None,
        symbols: list[str] | None = None,
        status: str | None = None,
    ) -> dict:
        items = self.bar_store.list_sync_runs(
            days=days,
            timeframe=timeframe,
            symbols=symbols,
            status=status,
        )
        return {"items": items}

