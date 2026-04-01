from application.market_data.sync_service import SyncService


class _FakeQuoteRepo:
    def fetch(self, symbols, as_of, timeframe):
        return []


class _FakeBarStore:
    def upsert_bars(self, rows):
        return 0


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
