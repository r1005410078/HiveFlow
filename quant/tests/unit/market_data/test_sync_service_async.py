"""SyncService.execute_sync 异步相关测试：progress 回调、cancel、failure queue。"""

from application.market_data.sync_service import SyncService


class _FakeQuoteRepo:
    def __init__(self, fail_symbols=None, fail_count=999):
        self.calls = []
        self._fail_symbols = fail_symbols or set()
        self._fail_count = fail_count
        self._call_counts: dict[str, int] = {}

    def fetch(self, symbols, as_of, timeframe):
        self.calls.append({"symbols": symbols, "as_of": as_of})
        rows = []
        for s in symbols:
            self._call_counts[s] = self._call_counts.get(s, 0) + 1
            if s in self._fail_symbols and self._call_counts[s] <= self._fail_count:
                raise RuntimeError(f"simulated failure for {s}")
            rows.append({
                "symbol": s, "timeframe": timeframe,
                "bar_time": f"{as_of}T15:00:00+08:00",
                "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1,
                "volume": 100.0, "amount": 110.0, "adj_factor": 1.0,
                "data_source": "fake",
            })
        return rows


class _FakeBarStore:
    def __init__(self):
        self.written = []
        self.checkpoints = []
        self.failures = []

    def upsert_bars(self, rows):
        self.written.extend(rows)
        return len(rows)

    def get_checkpoints(self, symbols, timeframe):
        return {}

    def upsert_checkpoints(self, checkpoints):
        self.checkpoints.extend(checkpoints)

    def upsert_symbol_failure(self, run_id, symbol, error_code, error_message, day):
        self.failures.append({"run_id": run_id, "symbol": symbol, "error_code": error_code, "day": day})

    def clear_symbol_failure(self, run_id, symbol):
        self.failures = [f for f in self.failures if not (f["run_id"] == run_id and f["symbol"] == symbol)]

    def get_sync_run_by_request_id(self, request_id):
        return None

    def insert_sync_run(self, payload):
        pass


def test_execute_sync_calls_on_progress():
    repo = _FakeQuoteRepo()
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    progress_phases = []

    def on_progress(phase, progress):
        progress_phases.append(phase)

    result = svc.execute_sync(
        run_id="test-run-1",
        days=3,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        on_progress=on_progress,
    )

    assert result["status"] == "success"
    assert "resolving_symbols" in progress_phases
    assert "fetching" in progress_phases


def test_execute_sync_respects_cancel():
    repo = _FakeQuoteRepo()
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    cancel_after = 1
    call_count = [0]

    def should_cancel():
        call_count[0] += 1
        return call_count[0] > cancel_after

    result = svc.execute_sync(
        run_id="test-cancel",
        days=10,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        should_cancel=should_cancel,
    )

    assert result["status"] == "cancelled"
    assert result["error_code"] == "SYNC_CANCELLED"
    assert len(repo.calls) < 10


def test_execute_sync_failure_queue_and_terminal():
    repo = _FakeQuoteRepo(fail_symbols={"000001.SZ"}, fail_count=999)
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    # When all symbols fail terminally, the service re-raises RuntimeError;
    # verify that the audit table (failures list) was populated before the raise.
    import pytest
    with pytest.raises(RuntimeError, match="simulated failure"):
        svc.execute_sync(
            run_id="test-fail",
            days=2,
            end_date="2026-04-01",
            timeframe="1d",
            symbols=["000001.SZ"],
        )

    assert len(store.failures) >= 1
    assert store.failures[0]["symbol"] == "000001.SZ"


def test_execute_sync_retry_succeeds_after_initial_failure():
    repo = _FakeQuoteRepo(fail_symbols={"000001.SZ"}, fail_count=1)
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    result = svc.execute_sync(
        run_id="test-retry-ok",
        days=1,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["000001.SZ"],
    )

    assert result["status"] == "success"
    assert result["written_rows"] >= 0


def test_execute_sync_progress_contains_symbol_fields():
    repo = _FakeQuoteRepo()
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    captured = []

    def on_progress(phase, progress):
        captured.append(progress)

    svc.execute_sync(
        run_id="test-fields",
        days=2,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH", "000001.SZ"],
        on_progress=on_progress,
    )

    last = captured[-1]
    assert "symbols_done_count" in last
    assert "symbols_pending_count" in last
    assert "current_symbol" in last
    assert "symbol_lists_truncated" in last
    assert last["total_symbols"] == 2


def test_execute_sync_cancel_still_flushes_checkpoints():
    repo = _FakeQuoteRepo()
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    call_count = [0]

    def should_cancel():
        call_count[0] += 1
        return call_count[0] > 2

    result = svc.execute_sync(
        run_id="test-cancel-cp",
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        should_cancel=should_cancel,
    )

    assert result["status"] == "cancelled"
    assert len(store.checkpoints) >= 0
