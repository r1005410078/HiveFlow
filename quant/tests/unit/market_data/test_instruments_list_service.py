from __future__ import annotations

import pytest

from application.market_data.instruments_list_service import InstrumentsListService
from application.market_data.symbol_names import resolve_quant_package_root
from application.market_data.universe_symbols import list_symbols_from_universe_file


def test_universe_mode_pages_and_cursor(monkeypatch, tmp_path) -> None:
    root = tmp_path / "quant"
    uni = root / "config" / "universes"
    uni.mkdir(parents=True)
    (uni / "follow.txt").write_text("600519.SH\n000001.SZ\n", encoding="utf-8")

    monkeypatch.setattr(
        "application.market_data.universe_symbols.resolve_quant_package_root",
        lambda: root,
    )

    svc = InstrumentsListService(bar_store=None)
    out = svc.list_instruments(mode="universe", universe="follow", limit=1)
    assert len(out["items"]) == 1
    assert out["has_more"] is True
    assert out["next_cursor_symbol"] == out["items"][0]["symbol"]

    out2 = svc.list_instruments(
        mode="universe",
        universe="follow",
        limit=10,
        cursor_symbol=out["next_cursor_symbol"],
    )
    assert len(out2["items"]) == 1
    assert out2["has_more"] is False


def test_universe_mode_requires_universe() -> None:
    svc = InstrumentsListService(bar_store=None)
    with pytest.raises(ValueError, match="INSTRUMENTS_UNIVERSE_REQUIRED"):
        svc.list_instruments(mode="universe", universe="")


def test_invalid_mode() -> None:
    svc = InstrumentsListService(bar_store=None)
    with pytest.raises(ValueError, match="INSTRUMENTS_INVALID_MODE"):
        svc.list_instruments(mode="fx")


def test_db_mode_requires_bar_store() -> None:
    svc = InstrumentsListService(bar_store=None)
    with pytest.raises(ValueError, match="INSTRUMENTS_DB_UNAVAILABLE"):
        svc.list_instruments(mode="db", start_date="2026-04-01", end_date="2026-04-01")


def test_db_mode_partial_dates_rejected() -> None:
    class _Store:
        def list_symbols_with_min_bars_in_window(self, **kwargs):
            return ([], False)

    svc = InstrumentsListService(bar_store=_Store())
    with pytest.raises(ValueError, match="INSTRUMENTS_DATE_WINDOW_INCOMPLETE"):
        svc.list_instruments(mode="db", start_date="2026-04-01", end_date=None)


def test_db_mode_uses_store() -> None:
    class _Store:
        def __init__(self):
            self.calls: list[dict] = []

        def list_symbols_with_min_bars_in_window(self, **kwargs):
            self.calls.append(kwargs)
            return (["600519.SH"], False)

    store = _Store()
    svc = InstrumentsListService(bar_store=store)
    out = svc.list_instruments(
        mode="db",
        start_date="2026-04-01",
        end_date="2026-04-02",
        min_bars=2,
        storage_timeframe="1m",
        limit=50,
        cursor_symbol=None,
    )
    assert len(out["items"]) == 1
    assert out["items"][0]["symbol"] == "600519.SH"
    assert store.calls[0]["min_bars"] == 2
    assert store.calls[0]["after_symbol"] is None


def test_list_symbols_follow_matches_repo_file() -> None:
    """Sanity: default quant root has follow.txt with expected shape."""
    path = resolve_quant_package_root() / "config" / "universes" / "follow.txt"
    if not path.exists():
        pytest.skip("follow.txt not in this checkout")
    syms = list_symbols_from_universe_file("follow")
    assert all(s.endswith((".SH", ".SZ", ".BJ")) for s in syms)
