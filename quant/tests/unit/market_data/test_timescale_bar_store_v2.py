from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore


class _FakeCursor:
    def __init__(self):
        self.executed: list[tuple[str, object]] = []
        self._rows = [("run_001", "2026-04-01", "success", "1d", 2)]

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
    assert out[0]["run_id"] == "run_001"
    assert out[0]["timeframe"] == "1d"
