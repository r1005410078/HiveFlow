from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self._rows = [
            ("2026-04-01 15:00:00+08", "600519.SH", "1d", 1450.0, 1468.0, 1442.0, 1459.44, 29125.0, 4256185472.0, "tencent")
        ]

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._rows

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
    assert out[0]["run_id"].startswith("bar_600519.SH_2026-04-01")
    assert out[0]["bar_time"].startswith("2026-04-01")
    assert out[0]["symbol"] == "600519.SH"
    assert out[0]["status"] == "success"
    assert out[0]["timeframe"] == "1d"
    assert out[0]["close"] == 1459.44


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
        "symbols_hash": "abc123",
        "effective_symbols_count": 2,
        "error_code": None,
        "error_message": None,
    }

    store.insert_sync_run(payload)

    assert conn.committed is True
    sql_text, params = conn.cursor_obj.executed[0]
    assert "insert into sync_runs" in sql_text.lower()
    assert params["run_id"] == payload["run_id"]
