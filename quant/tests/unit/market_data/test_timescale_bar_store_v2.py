from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore


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


class _FakeConn:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True


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
