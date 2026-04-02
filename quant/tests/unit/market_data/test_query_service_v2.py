from application.market_data.query_service import QueryService


class _FakeBarStore:
    def list_sync_runs(self, days, timeframe=None, status=None, request_id=None, limit=None):
        self.call_args = {
            "days": days,
            "timeframe": timeframe,
            "status": status,
            "request_id": request_id,
            "limit": limit,
        }
        return [
            {
                "run_id": "550e8400-e29b-41d4-a716-446655440000",
                "request_id": "req_001",
                "status": "success",
                "days": 5,
                "end_date": "2026-04-01",
                "timeframe": "1d",
                "effective_symbols_count": 2,
                "started_at": "2026-04-01T09:30:00+08:00",
                "finished_at": "2026-04-01T09:31:00+08:00",
                "error_code": None,
                "error_message": None,
            }
        ]


def test_query_service_returns_run_metadata_items() -> None:
    store = _FakeBarStore()
    svc = QueryService(bar_store=store)

    out = svc.query(days=5, timeframe="1d", status="success", request_id="req_001", limit=20)

    assert "items" in out
    assert store.call_args == {
        "days": 5,
        "timeframe": "1d",
        "status": "success",
        "request_id": "req_001",
        "limit": 20,
    }
    assert out["items"][0]["request_id"] == "req_001"
    assert out["items"][0]["effective_symbols_count"] == 2
    assert "close" not in out["items"][0]
