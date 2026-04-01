from application.market_data.query_service import QueryService


class _FakeBarStore:
    def list_sync_runs(self, days, timeframe=None, symbols=None, status=None):
        return [
            {
                "run_id": "run_001",
                "date": "2026-04-01",
                "status": "success",
                "timeframe": "1d",
                "symbols_count": 1,
                "manifest_id": "mf_001",
            }
        ]


def test_query_service_returns_items() -> None:
    """验证 query 服务返回 items 列表结构。"""
    svc = QueryService(bar_store=_FakeBarStore())

    out = svc.query(days=5, timeframe="1d")

    assert "items" in out
    assert len(out["items"]) == 1
    assert out["items"][0]["run_id"] == "run_001"
