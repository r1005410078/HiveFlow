"""SyncWorker 单元测试：串行互斥、双提交 409、异常写 run 终态。"""

import threading
import time

from application.market_data.sync_worker import SyncWorker


class _FakeBarStore:
    def __init__(self):
        self.runs_inserted = []
        self.progress_updates = []
        self.finalized = []
        self.cancel_requested = {}

    def insert_sync_run_running(self, payload):
        self.runs_inserted.append(payload)

    def update_sync_progress(self, run_id, phase, progress):
        self.progress_updates.append({"run_id": run_id, "phase": phase})

    def finalize_sync_run(self, run_id, status, **kwargs):
        self.finalized.append({"run_id": run_id, "status": status, **kwargs})

    def get_sync_run_by_id(self, run_id):
        return {"run_id": run_id, "cancel_requested_at": self.cancel_requested.get(run_id)}

    def get_sync_run_by_request_id(self, request_id):
        return None

    def get_checkpoints(self, symbols, timeframe):
        return {}

    def upsert_checkpoints(self, checkpoints):
        pass

    def upsert_bars(self, rows):
        return len(rows)

    def upsert_symbol_failure(self, *args, **kwargs):
        pass

    def mark_orphan_runs_interrupted(self):
        return 0


class _FakeQuoteRepo:
    def __init__(self, delay: float = 0):
        self._delay = delay

    def fetch(self, symbols, as_of, timeframe):
        if self._delay:
            time.sleep(self._delay)
        return [
            {
                "symbol": s, "timeframe": timeframe,
                "bar_time": f"{as_of}T15:00:00+08:00",
                "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1,
                "volume": 100.0, "amount": 110.0, "adj_factor": 1.0,
                "data_source": "fake",
            }
            for s in symbols
        ]


_store_instance = None


def _make_store_factory(store):
    def factory():
        return store
    return factory


def _make_repo_factory(delay=0):
    def factory():
        return _FakeQuoteRepo(delay=delay)
    return factory


def test_worker_submit_and_complete():
    store = _FakeBarStore()
    worker = SyncWorker(
        bar_store_factory=_make_store_factory(store),
        quote_repo_factory=_make_repo_factory(),
    )

    ok = worker.submit_sync("run-001", {
        "days": 2,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "symbols": ["600519.SH"],
    })
    assert ok is True

    worker.wait_for_completion(timeout=10)
    assert not worker.is_running()
    assert len(store.finalized) == 1
    assert store.finalized[0]["status"] == "success"


def test_worker_serial_rejects_second_submit():
    store = _FakeBarStore()
    worker = SyncWorker(
        bar_store_factory=_make_store_factory(store),
        quote_repo_factory=_make_repo_factory(delay=0.5),
    )

    ok1 = worker.submit_sync("run-001", {
        "days": 2,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "symbols": ["600519.SH"],
    })
    assert ok1 is True

    time.sleep(0.1)
    ok2 = worker.submit_sync("run-002", {
        "days": 2,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "symbols": ["000001.SZ"],
    })
    assert ok2 is False
    assert worker.current_run_id() == "run-001"

    worker.wait_for_completion(timeout=10)


def test_worker_handles_exception_gracefully():
    store = _FakeBarStore()

    def _bad_repo_factory():
        class _Repo:
            def fetch(self, **kw):
                raise RuntimeError("simulated failure")
        return _Repo()

    worker = SyncWorker(
        bar_store_factory=_make_store_factory(store),
        quote_repo_factory=_bad_repo_factory,
    )

    worker.submit_sync("run-fail", {
        "days": 1,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "symbols": ["600519.SH"],
    })
    worker.wait_for_completion(timeout=10)

    assert not worker.is_running()
    assert any(f["status"] in ("failed", "success") for f in store.finalized)


def test_worker_allows_new_submit_after_completion():
    store = _FakeBarStore()
    worker = SyncWorker(
        bar_store_factory=_make_store_factory(store),
        quote_repo_factory=_make_repo_factory(),
    )

    worker.submit_sync("run-a", {
        "days": 1, "end_date": "2026-04-01", "timeframe": "1d", "symbols": ["600519.SH"],
    })
    worker.wait_for_completion(timeout=10)

    ok = worker.submit_sync("run-b", {
        "days": 1, "end_date": "2026-04-01", "timeframe": "1d", "symbols": ["000001.SZ"],
    })
    assert ok is True
    worker.wait_for_completion(timeout=10)
    assert len(store.finalized) == 2
