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

    def upsert_bars(self, rows):
        self.written_rows.extend(rows)
        return len(rows)

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
    assert out["written_rows"] == 5
    assert len(svc.quote_repo.calls) == 5
    assert svc.quote_repo.calls[0]["as_of"] == "2026-03-28"
    assert svc.quote_repo.calls[-1]["as_of"] == "2026-04-01"


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


def test_sync_service_uses_default_watchlist_plus_positions_when_no_symbols_or_universe() -> None:
    """验证默认集合来自 watchlist + positions（并集去重）。"""
    svc = SyncService(quote_repo=_FakeQuoteRepo(), bar_store=_FakeBarStore())

    out = svc.sync(days=1, end_date="2026-04-01", timeframe="1d")

    # watchlist: 2 + positions: 2, 当前模板中无重复，期望 >= 4
    assert out["selection_mode"] == "default"
    assert out["effective_symbols_count"] >= 4


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
