from interfaces.adapters.market_data.timescale_bar_store import (
    TimescaleBarStore,
    enrich_sync_run_dict,
)


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self._rows = [
            (
                "run_600519.SH_2026-04-01",
                "req-1",
                "success",
                5,
                "2026-04-01",
                "1d",
                "symbols",
                "abc123",
                1,
                42,
                ["mf_001", "mf_002"],
                "2026-04-01T09:30:00+08:00",
                "2026-04-01T09:31:00+08:00",
                None,
                None,
            )
        ]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0]

    def close(self):
        return None


class _FakeCursorBars(_FakeCursor):
    """Cursor for bar reads: avoid returning sync_run-shaped rows from fetchall."""

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


class _FakeConnBars(_FakeConn):
    def __init__(self):
        super().__init__()
        self.cursor_obj = _FakeCursorBars()


class _FakeCursorSymbolAgg(_FakeCursorBars):
    def fetchall(self):
        return [("600519.SH",), ("000001.SZ",)]


def test_upsert_bars_uses_on_conflict_and_commits():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)
    rows = [
        {
            "symbol": "600519.SH",
            "timeframe": "1d",
            "bar_time": "2026-04-01T15:00:00+08:00",
            "open": 1.0,
            "high": 1.2,
            "low": 0.9,
            "close": 1.1,
            "volume": 10.0,
            "amount": 11.0,
            "adj_factor": 1.0,
            "data_source": "akshare",
        }
    ]

    written = store.upsert_bars(rows)

    assert written == 1
    assert conn.committed is True
    sql_text, _ = conn.cursor_obj.executed[0]
    assert "on conflict (symbol, timeframe, bar_time)" in sql_text.lower()


def test_list_sync_runs_returns_items_shape():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)

    out = store.list_sync_runs(days=5, timeframe="1d")

    assert len(out) == 1
    assert out[0]["run_id"].startswith("run_600519.SH_2026-04-01")
    assert out[0]["request_id"] == "req-1"
    assert out[0]["status"] == "success"
    assert out[0]["selection_mode"] == "symbols"
    assert out[0]["symbols_hash"] == "abc123"
    assert out[0]["timeframe"] == "1d"
    assert out[0]["written_rows"] == 42
    assert out[0]["manifest_ids"] == ["mf_001", "mf_002"]


def test_get_sync_run_by_request_id_returns_manifest_ids_shape():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)

    out = store.get_sync_run_by_request_id("req-1")

    assert out["request_id"] == "req-1"
    assert out["selection_mode"] == "symbols"
    assert out["written_rows"] == 42
    assert out["manifest_ids"] == ["mf_001", "mf_002"]


def test_insert_sync_run_executes_insert_and_commits():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)

    payload = {
        "run_id": "550e8400-e29b-41d4-a716-446655440000",
        "request_id": "req-1",
        "status": "success",
        "days": 5,
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "selection_mode": "symbols",
        "symbols_hash": "abc123",
        "effective_symbols_count": 2,
        "written_rows": 12,
        "manifest_ids": ["mf_001"],
        "error_code": None,
        "error_message": None,
    }

    store.insert_sync_run(payload)

    assert conn.committed is True
    sql_text, params = conn.cursor_obj.executed[0]
    assert "insert into sync_runs" in sql_text.lower()
    assert params["run_id"] == payload["run_id"]
    assert params["manifest_ids"] == payload["manifest_ids"]


def test_finalize_sync_run_updates_effective_symbols_count_and_hash():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)
    rid = "550e8400-e29b-41d4-a716-446655440000"
    store.finalize_sync_run(
        rid,
        "success",
        written_rows=0,
        manifest_ids=["mf_x"],
        progress={"total_symbols": 3},
        effective_symbols_count=3,
        symbols_hash="a" * 64,
    )
    assert conn.committed is True
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "effective_symbols_count" in sql_text
    assert "symbols_hash" in sql_text
    assert params[-1] == rid
    assert 3 in params
    assert ("a" * 64) in params


def test_enrich_sync_run_dict_fills_universe_placeholders_from_progress():
    d = {
        "selection_mode": "universe",
        "effective_symbols_count": 0,
        "symbols_hash": "",
        "progress": {
            "total_symbols": 3,
            "symbols_done_for_run": ["600519.SH", "000001.SZ", "600036.SH"],
            "symbols_pending_for_run": [],
        },
    }
    out = enrich_sync_run_dict(d)
    assert out["effective_symbols_count"] == 3
    assert len(out["symbols_hash"]) == 64


def test_finalize_sync_run_omits_optional_symbol_columns_when_not_passed():
    conn = _FakeConn()
    store = TimescaleBarStore(conn)
    rid = "550e8400-e29b-41d4-a716-446655440001"
    store.finalize_sync_run(
        rid,
        "failed",
        written_rows=0,
        error_code="X",
        error_message="y",
        progress={},
    )
    sql_text, _params = conn.cursor_obj.executed[-1]
    assert "effective_symbols_count" not in sql_text
    assert "symbols_hash" not in sql_text


def test_list_storage_bars_filters_timeframe_and_orders_asc():
    conn = _FakeConnBars()
    store = TimescaleBarStore(conn)
    store.list_storage_bars(order="asc")
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "timeframe = %s" in sql_text
    assert params[0] == "1m"
    assert "order by bar_time asc" in sql_text.lower()
    assert "symbol asc" in sql_text.lower()
    assert params[-1] == 5000


def test_list_storage_bars_orders_desc():
    conn = _FakeConnBars()
    store = TimescaleBarStore(conn)
    store.list_storage_bars(storage_timeframe="1m", order="desc")
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "timeframe = %s" in sql_text
    assert params[0] == "1m"
    assert "order by bar_time desc" in sql_text.lower()
    assert "symbol asc" in sql_text.lower()


def test_list_storage_bars_passes_bounds_and_custom_limit():
    conn = _FakeConnBars()
    store = TimescaleBarStore(conn)
    store.list_storage_bars(
        symbols=["600519.SH"],
        storage_timeframe="1m",
        start_date="2026-04-01",
        end_date="2026-04-02",
        limit=100,
        order="asc",
    )
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "symbol = any(%s)" in sql_text
    assert "2026-04-01T00:00:00+08:00" in params
    assert "2026-04-02T23:59:59+08:00" in params
    assert params[-1] == 100


def test_list_symbols_with_min_bars_pagination_has_more():
    conn = _FakeConnBars()
    conn.cursor_obj = _FakeCursorSymbolAgg()
    store = TimescaleBarStore(conn)
    syms, has_more = store.list_symbols_with_min_bars_in_window(
        storage_timeframe="1m",
        start_date="2026-04-01",
        end_date="2026-04-02",
        min_bars=1,
        after_symbol=None,
        limit=1,
    )
    assert syms == ["600519.SH"]
    assert has_more is True
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "GROUP BY symbol" in sql_text
    assert "HAVING COUNT(*)" in sql_text
    assert params[-1] == 2


def test_list_symbols_with_min_bars_after_cursor_in_sql():
    conn = _FakeConnBars()
    conn.cursor_obj = _FakeCursorSymbolAgg()
    store = TimescaleBarStore(conn)
    store.list_symbols_with_min_bars_in_window(
        storage_timeframe="1m",
        start_date="2026-04-01",
        end_date="2026-04-02",
        min_bars=1,
        after_symbol="600000.SH",
        limit=10,
    )
    sql_text, params = conn.cursor_obj.executed[-1]
    assert "symbol > %s" in sql_text
    assert "600000.SH" in params
