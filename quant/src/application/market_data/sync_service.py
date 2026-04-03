from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
import re
from uuid import uuid4

from domain.market_data.value_objects import validate_timeframe

_UNIVERSE_KEYS = ("csi300", "zz500", "all_a", "self_select", "follow")
_UNIVERSE_FILE_EXT = ".txt"

_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")


class SyncService:
    def __init__(self, quote_repo, bar_store, universe_source_repo=None):
        self.quote_repo = quote_repo
        self.bar_store = bar_store
        self.universe_source_repo = universe_source_repo

    def _config_root(self) -> Path:
        # quant/src/application/market_data/sync_service.py -> quant/
        return Path(__file__).resolve().parents[3]

    def _universe_dir(self) -> Path:
        return self._config_root() / "config" / "universes"

    @staticmethod
    def _universe_file_name(universe: str) -> str:
        return f"{universe}{_UNIVERSE_FILE_EXT}"

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

    def _parse_universe_file(self, universe: str) -> list[str]:
        if universe not in _UNIVERSE_KEYS:
            raise ValueError(f"unknown universe: {universe}")
        path = self._universe_dir() / self._universe_file_name(universe)
        if not path.exists():
            raise ValueError(f"unknown universe: {universe}")
        symbols: list[str] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            symbols.append(self._norm_symbol(line))
        normalized = sorted(set(symbols))
        if not normalized:
            raise ValueError(f"universe {universe} has no symbols")
        return normalized

    def _write_universe_file(self, universe: str, symbols: list[str]) -> Path:
        if universe not in _UNIVERSE_KEYS:
            raise ValueError(f"unknown universe: {universe}")
        normalized = sorted({self._norm_symbol(s) for s in symbols if s and s.strip()})
        if not normalized:
            raise ValueError(f"universe {universe} resolved empty symbols")
        universe_dir = self._universe_dir()
        universe_dir.mkdir(parents=True, exist_ok=True)
        path = universe_dir / self._universe_file_name(universe)
        path.write_text("\n".join(normalized) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _symbols_hash(symbols: list[str]) -> str:
        payload = ",".join(sorted(symbols)).encode("utf-8")
        return sha256(payload).hexdigest()

    @staticmethod
    def _as_of_window(end_date: str, days: int) -> list[str]:
        end = datetime.strptime(end_date, "%Y-%m-%d").date()
        start = end - timedelta(days=days - 1)
        return [(start + timedelta(days=i)).isoformat() for i in range(days)]

    @staticmethod
    def _parse_datetime(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def _checkpoint_start_date(self, last_bar_time: str, window_start: datetime.date) -> datetime.date:
        checkpoint_date = self._parse_datetime(last_bar_time).date() + timedelta(days=1)
        return max(window_start, checkpoint_date)

    def _build_sync_summary(
        self,
        *,
        request_id: str | None,
        timeframe: str,
        days: int,
        end_date: str,
        selection_mode: str,
        effective_symbols_count: int,
        symbols_hash: str,
        written_rows: int,
        manifest_ids: list[str],
        generated_at: str,
        run: dict | None = None,
    ) -> dict:
        run = run or {}
        return {
            "status": run.get("status", "success"),
            "run_id": run.get("run_id", ""),
            "request_id": run.get("request_id", request_id),
            "timeframe": run.get("timeframe", timeframe),
            "days": run.get("days", days),
            "end_date": run.get("end_date", end_date),
            "effective_symbols_count": run.get("effective_symbols_count", effective_symbols_count),
            "selection_mode": run.get("selection_mode", selection_mode),
            "symbols_hash": run.get("symbols_hash", symbols_hash),
            "written_rows": run.get("written_rows", written_rows),
            "manifest_ids": run.get("manifest_ids", manifest_ids),
            "generated_at": run.get("generated_at")
            or run.get("finished_at")
            or run.get("started_at")
            or generated_at,
        }

    def _resolve_effective_symbols(
        self,
        symbols: list[str] | None,
        universe: str | None,
    ) -> tuple[list[str], str]:
        if symbols:
            normalized = sorted({self._norm_symbol(s) for s in symbols if s and s.strip()})
            return normalized, "symbols"

        if universe:
            normalized = self._parse_universe_file(universe)
            return normalized, "universe"

        cfg = self._config_root() / "config"
        watchlist = self._parse_watchlist(cfg / "watchlist.yml")
        positions = self._parse_positions(cfg / "positions.yml")
        default_set = sorted(set(watchlist + positions))
        return default_set, "default"

    def sync_universe_symbols(self, universe: str, provider: str = "akshare") -> dict:
        if provider != "akshare":
            raise ValueError(f"unsupported provider: {provider}")
        if self.universe_source_repo is None:
            raise RuntimeError("universe source provider is unavailable")
        fetch = getattr(self.universe_source_repo, "fetch_universe_symbols", None)
        if not callable(fetch):
            raise RuntimeError("universe source provider is unavailable")
        symbols = fetch(universe=universe)
        path = self._write_universe_file(universe=universe, symbols=symbols)
        return {
            "universe": universe,
            "provider": provider,
            "symbols_count": len(symbols),
            "file_path": str(path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

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

        get_existing_run = getattr(self.bar_store, "get_sync_run_by_request_id", None)
        if request_id and callable(get_existing_run):
            existing_run = get_existing_run(request_id)
            if existing_run and existing_run.get("status") == "success":
                return self._build_sync_summary(
                    request_id=request_id,
                    timeframe=timeframe,
                    days=days,
                    end_date=end_date,
                    selection_mode=existing_run.get("selection_mode", ""),
                    effective_symbols_count=existing_run.get("effective_symbols_count", 0),
                    symbols_hash=existing_run.get("symbols_hash", ""),
                    written_rows=existing_run.get("written_rows", 0),
                    manifest_ids=existing_run.get("manifest_ids", []),
                    generated_at="",
                    run=existing_run,
                )

        effective_symbols, selection_mode = self._resolve_effective_symbols(symbols, universe)
        if not effective_symbols:
            raise ValueError("no market data fetched for requested scope")
        as_of_dates = self._as_of_window(end_date=end_date, days=days)
        window_start = datetime.strptime(as_of_dates[0], "%Y-%m-%d").date()
        checkpoint_starts: dict[str, datetime.date] = {symbol: window_start for symbol in effective_symbols}
        get_checkpoints = getattr(self.bar_store, "get_checkpoints", None)
        if callable(get_checkpoints):
            try:
                checkpoint_map = get_checkpoints(effective_symbols, timeframe) or {}
            except Exception:
                checkpoint_map = {}
            for symbol, last_bar_time in checkpoint_map.items():
                if symbol in checkpoint_starts and last_bar_time:
                    try:
                        checkpoint_starts[symbol] = self._checkpoint_start_date(last_bar_time, window_start)
                    except ValueError:
                        continue
        has_incremental_checkpoint = any(start_date > window_start for start_date in checkpoint_starts.values())

        total_written_rows = 0
        has_any_rows = False
        made_fetch_call = False
        last_provider_error: RuntimeError | None = None
        latest_bar_times: dict[str, datetime] = {}
        for as_of in as_of_dates:
            as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
            fetch_symbols = [symbol for symbol in effective_symbols if as_of_date >= checkpoint_starts[symbol]]
            if not fetch_symbols:
                continue
            made_fetch_call = True
            try:
                rows = self.quote_repo.fetch(symbols=fetch_symbols, as_of=as_of, timeframe=timeframe)
            except RuntimeError as exc:
                last_provider_error = exc
                continue
            if not rows:
                continue
            has_any_rows = True
            total_written_rows += self.bar_store.upsert_bars(rows)
            for row in rows:
                symbol = row.get("symbol")
                bar_time = row.get("bar_time")
                if not symbol or not bar_time:
                    continue
                try:
                    current_bar_time = self._parse_datetime(bar_time)
                except ValueError:
                    continue
                previous_bar_time = latest_bar_times.get(symbol)
                if previous_bar_time is None or current_bar_time > previous_bar_time:
                    latest_bar_times[symbol] = current_bar_time

        if not has_any_rows and made_fetch_call:
            if last_provider_error is not None:
                raise RuntimeError(str(last_provider_error)) from last_provider_error
            if not has_incremental_checkpoint:
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
            "selection_mode": selection_mode,
            "symbols_hash": self._symbols_hash(effective_symbols),
            "effective_symbols_count": len(effective_symbols),
            "written_rows": total_written_rows,
            "manifest_ids": [manifest_id],
            "error_code": None,
            "error_message": None,
        }
        insert_sync_run = getattr(self.bar_store, "insert_sync_run", None)
        if callable(insert_sync_run):
            try:
                insert_sync_run(sync_run_payload)
            except Exception:
                if request_id and callable(get_existing_run):
                    existing_run = get_existing_run(request_id)
                    if existing_run and existing_run.get("status") == "success":
                        return self._build_sync_summary(
                            request_id=request_id,
                            timeframe=timeframe,
                            days=days,
                            end_date=end_date,
                            selection_mode=existing_run.get("selection_mode", selection_mode),
                            effective_symbols_count=len(effective_symbols),
                            symbols_hash=existing_run.get("symbols_hash", sync_run_payload["symbols_hash"]),
                            written_rows=existing_run.get("written_rows", total_written_rows),
                            manifest_ids=existing_run.get("manifest_ids", []),
                            generated_at=now,
                            run=existing_run,
                        )
                raise

        upsert_checkpoints = getattr(self.bar_store, "upsert_checkpoints", None)
        if callable(upsert_checkpoints) and latest_bar_times:
            upsert_checkpoints(
                [
                    {
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "last_bar_time": bar_time.isoformat(),
                        "last_run_id": run_id,
                    }
                    for symbol, bar_time in latest_bar_times.items()
                ]
            )

        return self._build_sync_summary(
            request_id=request_id,
            timeframe=timeframe,
            days=days,
            end_date=end_date,
            selection_mode=selection_mode,
            effective_symbols_count=len(effective_symbols),
            symbols_hash=sync_run_payload["symbols_hash"],
            written_rows=total_written_rows,
            manifest_ids=[manifest_id],
            generated_at=now,
            run=sync_run_payload,
        )
