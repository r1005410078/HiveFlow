from application.market_data.sync_service import SyncService


class _FakeQuoteRepo:
    def __init__(self):
        self.calls = []

    def fetch(self, symbols, as_of, timeframe):
        self.calls.append({"symbols": symbols, "as_of": as_of, "timeframe": timeframe})
        rows = []
        for symbol in symbols:
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "bar_time": f"{as_of}T15:00:00+08:00" if timeframe == "1d" else f"{as_of}T09:31:00+08:00",
                    "open": 1.0,
                    "high": 1.2,
                    "low": 0.9,
                    "close": 1.1,
                    "volume": 100.0,
                    "amount": 110.0,
                    "adj_factor": 1.0,
                    "data_source": "akshare",
                }
            )
        return rows


class _FakeBarStore:
    def __init__(self):
        self.written_rows = []
        self.sync_runs = []
        self.checkpoints_calls = []
        self.upserted_checkpoints = []

    def upsert_bars(self, rows):
        self.written_rows.extend(rows)
        return len(rows)

    def get_sync_run_by_request_id(self, request_id):
        del request_id
        return None

    def get_checkpoints(self, symbols, timeframe):
        self.checkpoints_calls.append({"symbols": symbols, "timeframe": timeframe})
        return {}

    def upsert_checkpoints(self, checkpoints):
        self.upserted_checkpoints.extend(checkpoints)

    def insert_sync_run(self, payload):
        self.sync_runs.append(payload)


def test_sync_service_returns_run_summary() -> None:
    """验证 sync 服务返回最小成功摘要字段。"""
    svc = SyncService(quote_repo=_FakeQuoteRepo(), bar_store=_FakeBarStore())

    out = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
    )

    assert out["status"] == "success"
    assert out["effective_symbols_count"] == 1
    assert out["timeframe"] == "1d"
    assert out["days"] == 5
    assert out["selection_mode"] == "symbols"
    assert "symbols_hash" in out
    assert "request_id" in out
    assert out["request_id"] is None
    assert out["written_rows"] == 5
    assert len(out["manifest_ids"]) == 1
    assert out["manifest_ids"][0].startswith("mf_")
    assert len(svc.quote_repo.calls) == 5
    assert svc.quote_repo.calls[0]["as_of"] == "2026-03-28"
    assert svc.quote_repo.calls[-1]["as_of"] == "2026-04-01"


def test_sync_service_returns_existing_successful_run_for_request_id() -> None:
    """验证 request_id 幂等命中时直接返回已有成功结果。"""
    repo = _FakeQuoteRepo()

    class _IdempotentBarStore(_FakeBarStore):
        def get_sync_run_by_request_id(self, request_id):
            assert request_id == "req-123"
            return {
                "run_id": "run-existing",
                "request_id": "req-123",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "selection_mode": "symbols",
                "effective_symbols_count": 1,
                "written_rows": 13,
                "symbols_hash": "stored-hash",
                "manifest_ids": ["mf_stored_123"],
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
            }

    store = _IdempotentBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        request_id="req-123",
    )
    out_again = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        request_id="req-123",
    )

    assert out["run_id"] == "run-existing"
    assert out_again["run_id"] == "run-existing"
    assert out["request_id"] == "req-123"
    assert out["selection_mode"] == "symbols"
    assert out["written_rows"] == 13
    assert out["symbols_hash"] == "stored-hash"
    assert out["manifest_ids"] == ["mf_stored_123"]
    assert out_again["manifest_ids"] == ["mf_stored_123"]
    assert {
        "status",
        "run_id",
        "request_id",
        "timeframe",
        "days",
        "end_date",
        "effective_symbols_count",
        "selection_mode",
        "symbols_hash",
        "written_rows",
        "manifest_ids",
        "generated_at",
    }.issubset(out.keys())
    assert repo.calls == []
    assert store.written_rows == []
    assert store.sync_runs == []
    assert store.upserted_checkpoints == []


def test_sync_service_recovers_from_request_id_insert_conflict() -> None:
    """验证 request_id 插入冲突后重读到成功结果时不会抛 500。"""
    repo = _FakeQuoteRepo()

    class _ConflictThenReadBarStore(_FakeBarStore):
        def __init__(self):
            super().__init__()
            self.request_id_lookups = 0

        def get_sync_run_by_request_id(self, request_id):
            self.request_id_lookups += 1
            if self.request_id_lookups == 1:
                return None
            assert request_id == "req-456"
            return {
                "run_id": "run-existing",
                "request_id": "req-456",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "selection_mode": "symbols",
                "symbols_hash": "existing-hash",
                "effective_symbols_count": 1,
                "written_rows": 7,
                "manifest_ids": ["mf_conflict_123"],
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
            }

        def insert_sync_run(self, payload):
            self.sync_runs.append(payload)
            raise RuntimeError("duplicate key value violates unique constraint")

    store = _ConflictThenReadBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
        request_id="req-456",
    )

    assert out["run_id"] == "run-existing"
    assert out["request_id"] == "req-456"
    assert out["selection_mode"] == "symbols"
    assert out["symbols_hash"] == "existing-hash"
    assert out["written_rows"] == 7
    assert out["manifest_ids"] == ["mf_conflict_123"]
    assert len(out["manifest_ids"]) == 1
    assert store.request_id_lookups == 2
    assert store.upserted_checkpoints == []


def test_sync_service_writes_rows_for_1m_timeframe() -> None:
    """验证 1m 粒度会走 fetch + upsert 并返回写入行数。"""
    repo = _FakeQuoteRepo()
    store = _FakeBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(
        days=1,
        end_date="2026-04-01",
        timeframe="1m",
        symbols=["600519.SH", "000001.SZ"],
    )

    assert out["status"] == "success"
    assert out["timeframe"] == "1m"
    assert out["written_rows"] == 2
    assert len(store.written_rows) == 2
    assert len(store.sync_runs) == 1
    assert repo.calls[0]["timeframe"] == "1m"


def test_sync_service_uses_checkpoint_to_reduce_fetch_window() -> None:
    """验证 checkpoint 会把抓取窗口缩到缺失区间。"""
    repo = _FakeQuoteRepo()

    class _CheckpointBarStore(_FakeBarStore):
        def get_checkpoints(self, symbols, timeframe):
            super().get_checkpoints(symbols, timeframe)
            return {"600519.SH": "2026-03-30T15:00:00+08:00"}

    store = _CheckpointBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(
        days=5,
        end_date="2026-04-01",
        timeframe="1d",
        symbols=["600519.SH"],
    )

    assert out["written_rows"] == 2
    assert [call["as_of"] for call in repo.calls] == ["2026-03-31", "2026-04-01"]
    assert store.checkpoints_calls == [{"symbols": ["600519.SH"], "timeframe": "1d"}]


def test_sync_service_returns_success_when_incremental_window_has_no_new_rows() -> None:
    """验证增量窗口无新数据时返回成功（written_rows=0），避免误判失败。"""

    class _CheckpointOnlyBarStore(_FakeBarStore):
        def get_checkpoints(self, symbols, timeframe):
            super().get_checkpoints(symbols, timeframe)
            return {"600519.SH": "2026-03-31T15:00:00+08:00"}

    class _EmptyQuoteRepo:
        def __init__(self):
            self.calls = []

        def fetch(self, symbols, as_of, timeframe):
            self.calls.append({"symbols": symbols, "as_of": as_of, "timeframe": timeframe})
            return []

    repo = _EmptyQuoteRepo()
    store = _CheckpointOnlyBarStore()
    svc = SyncService(quote_repo=repo, bar_store=store)

    out = svc.sync(days=2, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])

    assert out["status"] == "success"
    assert out["written_rows"] == 0
    assert [call["as_of"] for call in repo.calls] == ["2026-04-01"]

def test_sync_service_uses_default_watchlist_plus_positions_when_no_symbols_or_universe() -> None:
    """验证默认集合来自 watchlist + positions（并集去重）。"""
    class _DeterministicSyncService(SyncService):
        def _parse_watchlist(self, path):
            del path
            return ["600519.SH", "000001.SZ"]

        def _parse_positions(self, path):
            del path
            return ["600036.SH", "600519.SH"]

    repo = _FakeQuoteRepo()
    svc = _DeterministicSyncService(quote_repo=repo, bar_store=_FakeBarStore())

    out = svc.sync(days=1, end_date="2026-04-01", timeframe="1d")

    assert out["selection_mode"] == "default"
    assert out["effective_symbols_count"] == 3
    assert repo.calls[0]["symbols"] == ["000001.SZ", "600036.SH", "600519.SH"]


def test_sync_service_universe_overrides_default_set() -> None:
    """验证传 universe 时，不走默认配置集合。"""
    svc = SyncService(quote_repo=_FakeQuoteRepo(), bar_store=_FakeBarStore())

    out = svc.sync(days=1, end_date="2026-04-01", timeframe="1d", universe="csi300")

    assert out["selection_mode"] == "universe"
    assert out["effective_symbols_count"] == 3


def test_sync_service_raises_when_no_rows_fetched() -> None:
    """验证同步 0 条数据时返回失败，避免误报成功。"""
    class _EmptyQuoteRepo:
        def fetch(self, symbols, as_of, timeframe):
            return []

    svc = SyncService(quote_repo=_EmptyQuoteRepo(), bar_store=_FakeBarStore())
    try:
        svc.sync(days=1, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])
    except ValueError as exc:
        assert "no market data fetched" in str(exc)
    else:
        raise AssertionError("expected ValueError for empty sync result")


def test_sync_service_days_changes_written_rows() -> None:
    """验证 days 影响同步范围，30天与90天写入量不同。"""
    repo_30 = _FakeQuoteRepo()
    store_30 = _FakeBarStore()
    svc_30 = SyncService(quote_repo=repo_30, bar_store=store_30)
    out_30 = svc_30.sync(days=30, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])

    repo_90 = _FakeQuoteRepo()
    store_90 = _FakeBarStore()
    svc_90 = SyncService(quote_repo=repo_90, bar_store=store_90)
    out_90 = svc_90.sync(days=90, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])

    assert out_90["written_rows"] > out_30["written_rows"]
    assert out_30["written_rows"] == 30
    assert out_90["written_rows"] == 90


def test_sync_service_continues_when_some_days_provider_fails() -> None:
    """验证按天同步时，部分日期数据源失败不会导致整次失败。"""

    class _PartiallyFailingQuoteRepo:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, timeframe
            if as_of == "2026-03-31":
                return [
                    {
                        "symbol": "600519.SH",
                        "timeframe": "1d",
                        "bar_time": "2026-03-31T15:00:00+08:00",
                        "open": 1.0,
                        "high": 1.2,
                        "low": 0.9,
                        "close": 1.1,
                        "volume": 100.0,
                        "amount": 110.0,
                        "adj_factor": 1.0,
                        "data_source": "tencent",
                    }
                ]
            raise RuntimeError("provider unavailable on this day")

    svc = SyncService(quote_repo=_PartiallyFailingQuoteRepo(), bar_store=_FakeBarStore())
    out = svc.sync(days=3, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])

    assert out["status"] == "success"
    assert out["written_rows"] == 1


def test_sync_service_raises_runtime_error_when_all_days_provider_fail() -> None:
    """验证所有日期都源失败时返回 provider 错误。"""

    class _AlwaysFailQuoteRepo:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            raise RuntimeError("provider unavailable")

    svc = SyncService(quote_repo=_AlwaysFailQuoteRepo(), bar_store=_FakeBarStore())
    try:
        svc.sync(days=3, end_date="2026-04-01", timeframe="1d", symbols=["600519.SH"])
    except RuntimeError as exc:
        assert "provider unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
