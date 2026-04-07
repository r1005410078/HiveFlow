from __future__ import annotations

from typing import Protocol


class QuoteRepository(Protocol):
    def fetch(self, symbols: list[str], as_of: str, timeframe: str) -> list[dict]:
        ...


class BarStore(Protocol):
    def upsert_bars(self, rows: list[dict]) -> int:
        ...

    def get_sync_run_by_request_id(self, request_id: str) -> dict | None:
        ...

    def get_checkpoints(self, symbols: list[str], timeframe: str) -> dict[str, str]:
        ...

    def upsert_checkpoints(self, checkpoints: list[dict]) -> None:
        ...

    def insert_sync_run(self, payload: dict) -> None:
        ...

    def list_sync_runs(
        self,
        days: int,
        timeframe: str | None = None,
        status: str | None = None,
        request_id: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        ...

    def list_bars(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        ...

    def list_storage_bars(
        self,
        symbols: list[str] | None = None,
        storage_timeframe: str = "15m",
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
        order: str = "asc",
    ) -> list[dict]:
        ...

    def list_symbols_with_min_bars_in_window(
        self,
        *,
        storage_timeframe: str,
        start_date: str,
        end_date: str,
        min_bars: int,
        after_symbol: str | None,
        limit: int,
    ) -> tuple[list[str], bool]:
        ...
