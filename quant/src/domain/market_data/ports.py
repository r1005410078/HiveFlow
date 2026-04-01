from __future__ import annotations

from typing import Protocol


class QuoteRepository(Protocol):
    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> list[dict]:
        ...


class BarStore(Protocol):
    def upsert_bars(self, rows: list[dict]) -> int:
        ...

    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        symbols: list[str] | None = None,
        status: str | None = None,
    ) -> list[dict]:
        ...

