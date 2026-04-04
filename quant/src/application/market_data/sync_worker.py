"""Background sync worker — single-threaded, serial execution, mutual exclusion."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class SyncWorker:
    """Manages a single background thread for market-data sync jobs.

    - Only one job at a time (bar sync and universe sync share the same lock).
    - submit() returns False if another job is running (caller maps to HTTP 409).
    - Each job creates its own DB connection via factories (no shared connection with
      the request thread).
    """

    def __init__(
        self,
        bar_store_factory: Callable[[], Any],
        quote_repo_factory: Callable[[], Any],
        universe_source_factory: Callable[[], Any | None] | None = None,
    ):
        self._bar_store_factory = bar_store_factory
        self._quote_repo_factory = quote_repo_factory
        self._universe_source_factory = universe_source_factory
        self._lock = threading.Lock()
        self._current_run_id: str | None = None
        self._thread: threading.Thread | None = None

    # ── public API ────────────────────────────────────────────

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def current_run_id(self) -> str | None:
        if self.is_running():
            return self._current_run_id
        return None

    def submit_sync(
        self,
        run_id: str,
        params: dict,
    ) -> bool:
        """Submit a bar-sync job. Returns False if another job is running."""
        if not self._lock.acquire(blocking=False):
            return False
        if self.is_running():
            self._lock.release()
            return False

        self._current_run_id = run_id
        self._thread = threading.Thread(
            target=self._run_sync_job,
            args=(run_id, params),
            daemon=True,
            name=f"sync-worker-{run_id[:8]}",
        )
        self._thread.start()
        return True

    def submit_universe_sync(
        self,
        run_id: str,
        params: dict,
    ) -> bool:
        """Submit a universe-sync job (shares the same lock as bar sync)."""
        if not self._lock.acquire(blocking=False):
            return False
        if self.is_running():
            self._lock.release()
            return False

        self._current_run_id = run_id
        self._thread = threading.Thread(
            target=self._run_universe_sync_job,
            args=(run_id, params),
            daemon=True,
            name=f"universe-sync-worker-{run_id[:8]}",
        )
        self._thread.start()
        return True

    def wait_for_completion(self, timeout: float | None = None) -> bool:
        """Block until current job finishes. For graceful shutdown."""
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout)
            return not t.is_alive()
        return True

    # ── internal job runners ──────────────────────────────────

    def _run_sync_job(self, run_id: str, params: dict) -> None:
        try:
            bar_store = self._bar_store_factory()
            quote_repo = self._quote_repo_factory()
            universe_source = (
                self._universe_source_factory() if self._universe_source_factory else None
            )

            from application.market_data.sync_service import SyncService

            svc = SyncService(
                quote_repo=quote_repo,
                bar_store=bar_store,
                universe_source_repo=universe_source,
            )

            def on_progress(phase: str, progress: dict) -> None:
                try:
                    bar_store.update_sync_progress(run_id, phase, progress)
                except Exception:
                    logger.warning("failed to update progress for run %s", run_id, exc_info=True)

            def should_cancel() -> bool:
                try:
                    run = bar_store.get_sync_run_by_id(run_id)
                    return run is not None and run.get("cancel_requested_at") is not None
                except Exception:
                    return False

            result = svc.execute_sync(
                run_id=run_id,
                days=params["days"],
                end_date=params["end_date"],
                timeframe=params["timeframe"],
                symbols=params.get("symbols"),
                universe=params.get("universe"),
                request_id=params.get("request_id"),
                on_progress=on_progress,
                should_cancel=should_cancel,
            )

            bar_store.finalize_sync_run(
                run_id,
                status=result["status"],
                written_rows=result.get("written_rows", 0),
                manifest_ids=result.get("manifest_ids"),
                error_code=result.get("error_code"),
                error_message=result.get("error_message"),
                progress=result.get("progress"),
            )

        except Exception as exc:
            logger.error("sync job %s failed: %s", run_id, exc, exc_info=True)
            try:
                bar_store = self._bar_store_factory()
                bar_store.finalize_sync_run(
                    run_id,
                    status="failed",
                    error_code="SYNC_UNHANDLED_ERROR",
                    error_message=str(exc)[:1000],
                )
            except Exception:
                logger.error("failed to write error status for run %s", run_id, exc_info=True)
        finally:
            self._current_run_id = None
            try:
                self._lock.release()
            except RuntimeError:
                pass

    def _run_universe_sync_job(self, run_id: str, params: dict) -> None:
        try:
            bar_store = self._bar_store_factory()
            quote_repo = self._quote_repo_factory()
            universe_source = (
                self._universe_source_factory() if self._universe_source_factory else None
            )

            from application.market_data.sync_service import SyncService

            svc = SyncService(
                quote_repo=quote_repo,
                bar_store=bar_store,
                universe_source_repo=universe_source,
            )

            result = svc.sync_universe_symbols(
                universe=params["universe"],
                provider=params.get("provider", "akshare"),
            )

            bar_store.finalize_sync_run(
                run_id,
                status="success",
                progress={"universe_result": result},
            )

        except Exception as exc:
            logger.error("universe sync job %s failed: %s", run_id, exc, exc_info=True)
            try:
                bar_store = self._bar_store_factory()
                bar_store.finalize_sync_run(
                    run_id,
                    status="failed",
                    error_code="UNIVERSE_SYNC_FAILED",
                    error_message=str(exc)[:1000],
                )
            except Exception:
                logger.error("failed to write error status for run %s", run_id, exc_info=True)
        finally:
            self._current_run_id = None
            try:
                self._lock.release()
            except RuntimeError:
                pass
