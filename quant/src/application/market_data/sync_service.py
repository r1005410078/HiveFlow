from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from application.market_data.symbol_names import resolve_quant_package_root
from application.market_data.universe_symbols import UNIVERSE_KEYS as _UNIVERSE_KEYS
from application.market_data.universe_symbols import norm_exchange_symbol
from domain.market_data.value_objects import validate_timeframe
# Universes that akshare can fetch with optional Chinese names (symbol_names.json merge).
_AKSHARE_SYMBOL_NAME_UNIVERSES = ("csi300", "zz500", "all_a")
_UNIVERSE_FILE_EXT = ".txt"
_SYMBOL_NAMES_JSON = "symbol_names.json"

MAX_SYMBOL_ATTEMPTS = 3
PROGRESS_LIST_TRUNCATE_N = 200
RETRY_BACKOFF_SECONDS = 2.0


class SyncService:
    def __init__(self, quote_repo, bar_store, universe_source_repo=None):
        self.quote_repo = quote_repo
        self.bar_store = bar_store
        self.universe_source_repo = universe_source_repo

    # ── config / file helpers (unchanged) ─────────────────────

    def _config_root(self) -> Path:
        return resolve_quant_package_root()

    def _universe_dir(self) -> Path:
        return self._config_root() / "config" / "universes"

    @staticmethod
    def _universe_file_name(universe: str) -> str:
        return f"{universe}{_UNIVERSE_FILE_EXT}"

    @staticmethod
    def _norm_symbol(symbol: str) -> str:
        return norm_exchange_symbol(symbol)

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
        from application.market_data.universe_symbols import list_symbols_from_universe_file

        return list_symbols_from_universe_file(universe)

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

    def _symbol_names_json_path(self) -> Path:
        return self._universe_dir() / _SYMBOL_NAMES_JSON

    def _merge_symbol_names_json(self, updates: dict[str, str]) -> Path | None:
        """Merge symbol -> Chinese short name; empty values are skipped."""
        if not updates:
            return None
        path = self._symbol_names_json_path()
        existing: dict[str, str] = {}
        if path.is_file():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    existing = {str(k): str(v) for k, v in raw.items() if v is not None}
            except (json.JSONDecodeError, OSError):
                existing = {}
        for sym, name in updates.items():
            if not name or not str(name).strip():
                continue
            existing[self._norm_symbol(sym)] = str(name).strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        ordered = dict(sorted(existing.items()))
        path.write_text(json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        **kwargs,
    ) -> dict:
        run = run or {}
        summary: dict = {
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
        for k in ("error_code", "error_message"):
            if k in kwargs:
                summary[k] = kwargs[k]
            elif run.get(k) is not None:
                summary[k] = run[k]
        return summary

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

    # ── progress helpers ──────────────────────────────────────

    @staticmethod
    def _truncated_list(items: list[str], n: int = PROGRESS_LIST_TRUNCATE_N) -> tuple[list[str], bool]:
        s = sorted(items)
        if len(s) <= n:
            return s, False
        return s[:n], True

    @staticmethod
    def _classify_symbols(
        effective_symbols: list[str],
        checkpoint_starts: dict[str, object],
        as_of_dates: list[str],
        completed_days_index: int,
    ) -> tuple[list[str], list[str]]:
        """Split symbols into done / pending for current progress."""
        if not as_of_dates:
            return list(effective_symbols), []
        last_date_str = as_of_dates[-1]
        last_date = datetime.strptime(last_date_str, "%Y-%m-%d").date()
        done: list[str] = []
        pending: list[str] = []
        for sym in effective_symbols:
            start = checkpoint_starts.get(sym)
            if start is not None and start > last_date:
                done.append(sym)
            elif completed_days_index >= len(as_of_dates):
                done.append(sym)
            else:
                pending.append(sym)
        return done, pending

    def _build_progress_dict(
        self,
        *,
        effective_symbols: list[str],
        checkpoint_starts: dict,
        as_of_dates: list[str],
        completed_days: int,
        current_day: str | None,
        current_symbol: str | None,
        total_rows_written: int,
        start_time: float,
        failure_queue: list[dict],
        terminal_failed_count: int,
        symbol_errors: list[dict],
    ) -> dict:
        done, pending = self._classify_symbols(
            effective_symbols, checkpoint_starts, as_of_dates, completed_days,
        )
        done_trunc, trunc_done = self._truncated_list(done)
        pending_trunc, trunc_pending = self._truncated_list(pending)
        truncated = trunc_done or trunc_pending

        elapsed = time.monotonic() - start_time
        total_days = len(as_of_dates)
        eta = None
        if completed_days > 0 and completed_days < total_days:
            eta = round(elapsed / completed_days * (total_days - completed_days), 1)

        return {
            "total_symbols": len(effective_symbols),
            "total_rows_written": total_rows_written,
            "current_day": current_day,
            "total_days": total_days,
            "completed_days": completed_days,
            "current_symbol": current_symbol,
            "symbols_done_for_run": done_trunc,
            "symbols_pending_for_run": pending_trunc,
            "symbols_done_count": len(done),
            "symbols_pending_count": len(pending),
            "symbol_lists_truncated": truncated,
            "elapsed_seconds": round(elapsed, 1),
            "estimated_remaining_seconds": eta,
            "symbol_errors": symbol_errors[-50:],
            "failure_queue_depth": len(failure_queue),
            "terminal_failed_symbols_count": terminal_failed_count,
        }

    # ── universe sync (unchanged) ─────────────────────────────

    def _fetch_universe_symbol_name_updates(self, universe: str) -> tuple[list[str], dict[str, str]]:
        """Pull symbol -> name map from universe_source; no file writes."""
        if self.universe_source_repo is None:
            raise RuntimeError("universe source provider is unavailable")
        fetch_pairs = getattr(self.universe_source_repo, "fetch_universe_symbols_with_names", None)
        if callable(fetch_pairs):
            pairs = fetch_pairs(universe=universe)
            symbols = [s for s, _ in pairs]
            updates = {s: n for s, n in pairs}
            return symbols, updates
        fetch = getattr(self.universe_source_repo, "fetch_universe_symbols", None)
        if not callable(fetch):
            raise RuntimeError("universe source provider is unavailable")
        symbols = fetch(universe=universe)
        updates = {s: "" for s in symbols}
        return symbols, updates

    def merge_symbol_names_only(
        self,
        *,
        universes: list[str] | None = None,
        provider: str = "akshare",
    ) -> dict:
        """Merge ``symbol_names.json`` from akshare for given universes (default: csi300, zz500, all_a).

        Does not modify ``quant/config/universes/*.txt``.
        """
        if provider != "akshare":
            raise ValueError(f"unsupported provider: {provider}")
        raw_targets = list(universes) if universes else list(_AKSHARE_SYMBOL_NAME_UNIVERSES)
        seen: set[str] = set()
        targets: list[str] = []
        for u in raw_targets:
            u = str(u).strip()
            if not u or u in seen:
                continue
            seen.add(u)
            targets.append(u)
        if not targets:
            targets = list(_AKSHARE_SYMBOL_NAME_UNIVERSES)
        allowed = set(_AKSHARE_SYMBOL_NAME_UNIVERSES)
        for u in targets:
            if u not in allowed:
                raise ValueError(
                    "universe does not support symbol-name sync via akshare: "
                    f"{u} (allowed: {', '.join(_AKSHARE_SYMBOL_NAME_UNIVERSES)})"
                )
        names_path: Path | None = None
        per_universe: dict[str, int] = {}
        failed: list[dict[str, str]] = []
        for u in targets:
            try:
                _symbols, updates = self._fetch_universe_symbol_name_updates(u)
                merged = self._merge_symbol_names_json(updates)
                if merged is not None:
                    names_path = merged
                per_universe[u] = len(updates)
            except Exception as exc:
                failed.append({"universe": u, "message": str(exc)[:800]})
        if not per_universe:
            raise RuntimeError(
                "symbol_names sync failed for every universe: "
                + "; ".join(f"{item['universe']}: {item['message'][:200]}" for item in failed)
            )
        status = "ok" if not failed else "partial"
        out: dict = {
            "status": status,
            "provider": provider,
            "universes": targets,
            "per_universe_symbols": per_universe,
            "symbol_names_path": str(names_path) if names_path else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if failed:
            out["failed_universes"] = failed
        return out

    def sync_universe_symbols(self, universe: str, provider: str = "akshare") -> dict:
        if provider != "akshare":
            raise ValueError(f"unsupported provider: {provider}")
        symbols, updates = self._fetch_universe_symbol_name_updates(universe)
        merged = self._merge_symbol_names_json(updates)
        names_path = str(merged) if merged else None
        path = self._write_universe_file(universe=universe, symbols=symbols)
        out = {
            "universe": universe,
            "provider": provider,
            "symbols_count": len(symbols),
            "file_path": str(path),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if names_path:
            out["symbol_names_path"] = names_path
        return out

    # ── execute_sync (extracted core loop with callbacks) ─────

    def execute_sync(
        self,
        *,
        run_id: str,
        days: int,
        end_date: str,
        timeframe: str,
        symbols: list[str] | None = None,
        universe: str | None = None,
        request_id: str | None = None,
        on_progress: Callable[[str, dict], None] | None = None,
        should_cancel: Callable[[], bool] | None = None,
    ) -> dict:
        """Core sync loop with progress, cancel, and failure queue support.

        Returns the final sync summary dict (same shape as sync()).
        Raises ValueError / RuntimeError on unrecoverable issues.
        """
        validate_timeframe(timeframe)
        start_time = time.monotonic()

        # ── resolve symbols ───────────────────────────────────
        if on_progress:
            on_progress("resolving_symbols", {"total_symbols": 0})

        effective_symbols, selection_mode = self._resolve_effective_symbols(symbols, universe)
        if not effective_symbols:
            raise ValueError("no market data fetched for requested scope")

        as_of_dates = self._as_of_window(end_date=end_date, days=days)
        window_start = datetime.strptime(as_of_dates[0], "%Y-%m-%d").date()
        checkpoint_starts: dict[str, datetime.date] = {s: window_start for s in effective_symbols}

        get_checkpoints = getattr(self.bar_store, "get_checkpoints", None)
        if callable(get_checkpoints):
            try:
                checkpoint_map = get_checkpoints(effective_symbols, timeframe) or {}
            except Exception:
                checkpoint_map = {}
            for sym, last_bar_time in checkpoint_map.items():
                if sym in checkpoint_starts and last_bar_time:
                    try:
                        checkpoint_starts[sym] = self._checkpoint_start_date(last_bar_time, window_start)
                    except ValueError:
                        continue

        # ── main fetch loop ───────────────────────────────────
        total_written_rows = 0
        has_any_rows = False
        made_fetch_call = False
        last_provider_error: RuntimeError | None = None
        latest_bar_times: dict[str, datetime] = {}
        symbol_errors: list[dict] = []
        failure_queue: list[dict] = []
        failure_attempts: dict[str, int] = {}
        terminal_failed: set[str] = set()

        for day_idx, as_of in enumerate(as_of_dates):
            if should_cancel and should_cancel():
                break

            as_of_date = datetime.strptime(as_of, "%Y-%m-%d").date()
            fetch_symbols = [s for s in effective_symbols if as_of_date >= checkpoint_starts[s]]
            if not fetch_symbols:
                if on_progress:
                    progress = self._build_progress_dict(
                        effective_symbols=effective_symbols,
                        checkpoint_starts=checkpoint_starts,
                        as_of_dates=as_of_dates,
                        completed_days=day_idx + 1,
                        current_day=as_of,
                        current_symbol=None,
                        total_rows_written=total_written_rows,
                        start_time=start_time,
                        failure_queue=failure_queue,
                        terminal_failed_count=len(terminal_failed),
                        symbol_errors=symbol_errors,
                    )
                    on_progress("fetching", progress)
                continue

            made_fetch_call = True
            current_symbol = fetch_symbols[0] if fetch_symbols else None

            try:
                rows = self.quote_repo.fetch(symbols=fetch_symbols, as_of=as_of, timeframe=timeframe)
            except RuntimeError as exc:
                last_provider_error = exc
                for sym in fetch_symbols:
                    self._record_symbol_failure(
                        run_id=run_id, symbol=sym, day=as_of,
                        error_code="RUNTIME_ERROR", error_message=str(exc)[:500],
                        failure_attempts=failure_attempts,
                        failure_queue=failure_queue,
                        terminal_failed=terminal_failed,
                        symbol_errors=symbol_errors,
                    )
                continue

            if rows:
                has_any_rows = True
                total_written_rows += self.bar_store.upsert_bars(rows)
                fetched_symbols_set = set()
                for row in rows:
                    sym = row.get("symbol")
                    bar_time = row.get("bar_time")
                    if not sym or not bar_time:
                        continue
                    fetched_symbols_set.add(sym)
                    try:
                        current_bar_time = self._parse_datetime(bar_time)
                    except ValueError:
                        continue
                    prev = latest_bar_times.get(sym)
                    if prev is None or current_bar_time > prev:
                        latest_bar_times[sym] = current_bar_time

                empty_symbols = [s for s in fetch_symbols if s not in fetched_symbols_set]
                for sym in empty_symbols:
                    self._record_symbol_failure(
                        run_id=run_id, symbol=sym, day=as_of,
                        error_code="EMPTY_ROWS", error_message=f"no data returned for {as_of}",
                        failure_attempts=failure_attempts,
                        failure_queue=failure_queue,
                        terminal_failed=terminal_failed,
                        symbol_errors=symbol_errors,
                    )

            if on_progress:
                progress = self._build_progress_dict(
                    effective_symbols=effective_symbols,
                    checkpoint_starts=checkpoint_starts,
                    as_of_dates=as_of_dates,
                    completed_days=day_idx + 1,
                    current_day=as_of,
                    current_symbol=current_symbol,
                    total_rows_written=total_written_rows,
                    start_time=start_time,
                    failure_queue=failure_queue,
                    terminal_failed_count=len(terminal_failed),
                    symbol_errors=symbol_errors,
                )
                on_progress("fetching", progress)

            # Periodic checkpoint flush (every 10 days of progress)
            if (day_idx + 1) % 10 == 0:
                self._flush_checkpoints(latest_bar_times, timeframe, run_id)

        # ── retry pass for failure queue ──────────────────────
        retryable = [
            item for item in failure_queue
            if item["symbol"] not in terminal_failed
        ]
        if retryable and not (should_cancel and should_cancel()):
            time.sleep(RETRY_BACKOFF_SECONDS)
            for item in retryable:
                if should_cancel and should_cancel():
                    break
                sym = item["symbol"]
                day = item["day"]
                try:
                    rows = self.quote_repo.fetch(symbols=[sym], as_of=day, timeframe=timeframe)
                except RuntimeError as exc:
                    self._record_symbol_failure(
                        run_id=run_id, symbol=sym, day=day,
                        error_code="RUNTIME_ERROR", error_message=str(exc)[:500],
                        failure_attempts=failure_attempts,
                        failure_queue=failure_queue,
                        terminal_failed=terminal_failed,
                        symbol_errors=symbol_errors,
                    )
                    continue
                if rows:
                    has_any_rows = True
                    total_written_rows += self.bar_store.upsert_bars(rows)
                    for row in rows:
                        bar_sym = row.get("symbol")
                        bar_time = row.get("bar_time")
                        if bar_sym and bar_time:
                            try:
                                t = self._parse_datetime(bar_time)
                            except ValueError:
                                continue
                            prev = latest_bar_times.get(bar_sym)
                            if prev is None or t > prev:
                                latest_bar_times[bar_sym] = t
                    failure_queue[:] = [f for f in failure_queue if f["symbol"] != sym or f["day"] != day]
                    clear_fn = getattr(self.bar_store, "clear_symbol_failure", None)
                    if callable(clear_fn):
                        try:
                            clear_fn(run_id, sym)
                        except Exception:
                            pass

        # ── determine final status ────────────────────────────
        was_cancelled = should_cancel and should_cancel()

        if was_cancelled:
            final_status = "cancelled"
            error_code = "SYNC_CANCELLED"
            error_message = "cancelled by user"
        elif not has_any_rows and made_fetch_call:
            if last_provider_error is not None:
                raise RuntimeError(str(last_provider_error)) from last_provider_error
            # Data source returned no rows but no errors (e.g., 1m not available
            # for historical dates, non-trading days, or full-window holiday).
            # This is not a programming error — succeed with a diagnostic code.
            final_status = "success"
            error_code = "NO_DATA_RETURNED"
            error_message = (
                "data source returned no rows for the requested scope/timeframe "
                f"(symbols={len(effective_symbols)}, days={days}, timeframe={timeframe})"
            )
        else:
            final_status = "success"
            error_code = None
            error_message = None

        # ── flush checkpoints ─────────────────────────────────
        self._flush_checkpoints(latest_bar_times, timeframe, run_id)

        manifest_id = f"mf_{uuid4().hex[:10]}"
        now = datetime.now(timezone.utc).isoformat()

        final_progress = self._build_progress_dict(
            effective_symbols=effective_symbols,
            checkpoint_starts=checkpoint_starts,
            as_of_dates=as_of_dates,
            completed_days=len(as_of_dates) if not was_cancelled else 0,
            current_day=None,
            current_symbol=None,
            total_rows_written=total_written_rows,
            start_time=start_time,
            failure_queue=failure_queue,
            terminal_failed_count=len(terminal_failed),
            symbol_errors=symbol_errors,
        )

        return {
            "status": final_status,
            "run_id": run_id,
            "request_id": request_id,
            "timeframe": timeframe,
            "days": days,
            "end_date": end_date,
            "selection_mode": selection_mode,
            "effective_symbols_count": len(effective_symbols),
            "symbols_hash": self._symbols_hash(effective_symbols),
            "written_rows": total_written_rows,
            "manifest_ids": [manifest_id],
            "generated_at": now,
            "error_code": error_code,
            "error_message": error_message,
            "progress": final_progress,
        }

    def _record_symbol_failure(
        self,
        *,
        run_id: str,
        symbol: str,
        day: str,
        error_code: str,
        error_message: str,
        failure_attempts: dict[str, int],
        failure_queue: list[dict],
        terminal_failed: set[str],
        symbol_errors: list[dict],
    ) -> None:
        failure_attempts[symbol] = failure_attempts.get(symbol, 0) + 1
        attempts = failure_attempts[symbol]

        symbol_errors.append({"symbol": symbol, "day": day, "error": error_message})

        upsert_fn = getattr(self.bar_store, "upsert_symbol_failure", None)
        if callable(upsert_fn):
            try:
                upsert_fn(run_id, symbol, error_code, error_message, day)
            except Exception:
                pass

        if attempts >= MAX_SYMBOL_ATTEMPTS:
            terminal_failed.add(symbol)
            failure_queue[:] = [f for f in failure_queue if f["symbol"] != symbol]
        else:
            existing = [f for f in failure_queue if f["symbol"] == symbol and f["day"] == day]
            if not existing:
                failure_queue.append({
                    "symbol": symbol,
                    "day": day,
                    "enqueued_at": datetime.now(timezone.utc).isoformat(),
                    "reason_code": error_code,
                    "reason_message": error_message,
                    "attempts_in_run": attempts,
                })
            else:
                for f in existing:
                    f["reason_code"] = error_code
                    f["reason_message"] = error_message
                    f["attempts_in_run"] = attempts

    def _flush_checkpoints(
        self, latest_bar_times: dict[str, datetime], timeframe: str, run_id: str,
    ) -> None:
        upsert_checkpoints = getattr(self.bar_store, "upsert_checkpoints", None)
        if callable(upsert_checkpoints) and latest_bar_times:
            upsert_checkpoints([
                {
                    "symbol": sym,
                    "timeframe": timeframe,
                    "last_bar_time": bt.isoformat(),
                    "last_run_id": run_id,
                }
                for sym, bt in latest_bar_times.items()
            ])

    # ── sync() — backward-compatible wrapper ──────────────────

    def sync(
        self,
        days: int,
        end_date: str,
        timeframe: str,
        symbols: list[str] | None = None,
        universe: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        """Original synchronous sync — used by _InMemoryBarStore path and tests."""
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

        run_id = str(uuid4())
        result = self.execute_sync(
            run_id=run_id,
            days=days,
            end_date=end_date,
            timeframe=timeframe,
            symbols=symbols,
            universe=universe,
            request_id=request_id,
        )

        sync_run_payload = {
            "run_id": run_id,
            "request_id": request_id,
            "status": result["status"],
            "days": days,
            "end_date": end_date,
            "timeframe": timeframe,
            "selection_mode": result["selection_mode"],
            "symbols_hash": result["symbols_hash"],
            "effective_symbols_count": result["effective_symbols_count"],
            "written_rows": result["written_rows"],
            "manifest_ids": result["manifest_ids"],
            "error_code": result.get("error_code"),
            "error_message": result.get("error_message"),
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
                            selection_mode=existing_run.get("selection_mode", result["selection_mode"]),
                            effective_symbols_count=result["effective_symbols_count"],
                            symbols_hash=existing_run.get("symbols_hash", result["symbols_hash"]),
                            written_rows=existing_run.get("written_rows", result["written_rows"]),
                            manifest_ids=existing_run.get("manifest_ids", []),
                            generated_at=result["generated_at"],
                            run=existing_run,
                        )
                raise

        return self._build_sync_summary(
            request_id=request_id,
            timeframe=timeframe,
            days=days,
            end_date=end_date,
            selection_mode=result["selection_mode"],
            effective_symbols_count=result["effective_symbols_count"],
            symbols_hash=result["symbols_hash"],
            written_rows=result["written_rows"],
            manifest_ids=result["manifest_ids"],
            generated_at=result["generated_at"],
            error_code=result.get("error_code"),
            error_message=result.get("error_message"),
            run=sync_run_payload,
        )
