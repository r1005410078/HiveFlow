from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from domain.market_data.value_objects import validate_timeframe

_UNIVERSE_MAP: dict[str, list[str]] = {
    "csi300": ["600519.SH", "000001.SZ", "600036.SH"],
    "zz500": ["000001.SZ", "002475.SZ"],
    "all_a": ["000001.SZ", "600000.SH", "600519.SH"],
}

_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")


class SyncService:
    def __init__(self, quote_repo, bar_store):
        self.quote_repo = quote_repo
        self.bar_store = bar_store

    def _config_root(self) -> Path:
        # quant/src/application/market_data/sync_service.py -> quant/
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _norm_symbol(symbol: str) -> str:
        s = symbol.strip().upper()
        if not s:
            return ""
        if not _SYMBOL_PATTERN.match(s):
            raise ValueError(f"invalid symbol format: {symbol}")
        return s

    def _parse_watchlist(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        symbols: list[str] = []
        in_symbols = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line == "symbols:":
                in_symbols = True
                continue
            if in_symbols:
                if not line.startswith("-"):
                    break
                value = line.lstrip("-").strip().strip('"').strip("'")
                if value:
                    symbols.append(self._norm_symbol(value))
        return symbols

    def _parse_positions(self, path: Path) -> list[str]:
        if not path.exists():
            return []
        symbols: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("- symbol:") or line.startswith("symbol:"):
                value = line.split(":", 1)[1].strip().strip('"').strip("'")
                if value:
                    symbols.append(self._norm_symbol(value))
        return symbols

    @staticmethod
    def _symbols_hash(symbols: list[str]) -> str:
        payload = ",".join(sorted(symbols)).encode("utf-8")
        return sha256(payload).hexdigest()

    @staticmethod
    def _as_of_window(end_date: str, days: int) -> list[str]:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        start = end - timedelta(days=days - 1)
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]

    def _resolve_effective_symbols(
        self,
        symbols: list[str] | None,
        universe: str | None,
    ) -> tuple[list[str], str]:
        if symbols:
            normalized = sorted({self._norm_symbol(s) for s in symbols if s and s.strip()})
            return normalized, "symbols"

        if universe:
            if universe not in _UNIVERSE_MAP:
                raise ValueError(f"unknown universe: {universe}")
            normalized = sorted({_s for _s in _UNIVERSE_MAP[universe]})
            return normalized, "universe"

        cfg = self._config_root() / "config"
        watchlist = self._parse_watchlist(cfg / "watchlist.yml")
        positions = self._parse_positions(cfg / "positions.yml")
        default_set = sorted(set(watchlist + positions))
        return default_set, "default"

    def sync(
        self,
        days: int,
        end_date: str,
        timeframe: str,
        symbols: list[str] | None = None,
        universe: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        validate_timeframe(timeframe)
        effective_symbols, selection_mode = self._resolve_effective_symbols(symbols, universe)
        as_of_dates = self._as_of_window(end_date=end_date, days=days)
        total_written_rows = 0
        has_any_rows = False
        last_provider_error: RuntimeError | None = None
        for as_of in as_of_dates:
            try:
                rows = self.quote_repo.fetch(symbols=effective_symbols, as_of=as_of, timeframe=timeframe)
            except RuntimeError as exc:
                last_provider_error = exc
                continue
            if not rows:
                continue
            has_any_rows = True
            total_written_rows += self.bar_store.upsert_bars(rows)

        if not has_any_rows:
            if last_provider_error is not None:
                raise RuntimeError(str(last_provider_error)) from last_provider_error
            raise ValueError("no market data fetched for requested scope")
        run_id = str(uuid4())
        manifest_id = f"mf_{uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()
        sync_run_payload = {
            "run_id": run_id,
            "request_id": request_id,
            "status": "success",
            "days": days,
            "end_date": end_date,
            "timeframe": timeframe,
            "symbols_hash": self._symbols_hash(effective_symbols),
            "effective_symbols_count": len(effective_symbols),
            "error_code": None,
            "error_message": None,
        }
        insert_sync_run = getattr(self.bar_store, "insert_sync_run", None)
        if callable(insert_sync_run):
            insert_sync_run(sync_run_payload)

        return {
            "status": "success",
            "run_id": run_id,
            "timeframe": timeframe,
            "days": days,
            "end_date": end_date,
            "effective_symbols_count": len(effective_symbols),
            "selection_mode": selection_mode,
            "symbols_hash": sync_run_payload["symbols_hash"],
            "written_rows": total_written_rows,
            "manifest_ids": [manifest_id],
            "generated_at": now,
        }
