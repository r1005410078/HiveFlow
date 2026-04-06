from unittest.mock import MagicMock

import pytest

from application.market_data.coverage_service import get_coverage


def _make_bar_store(symbols: list[str]) -> MagicMock:
    store = MagicMock()
    store.list_symbols_with_min_bars_in_window.return_value = (symbols, False)
    return store


def test_full_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    symbols = ["000625.SZ", "300750.SZ"]
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: symbols,
    )
    result = get_coverage("default", _make_bar_store(symbols), "2025-01-01", "2026-01-01")
    assert result["coverage_rate"] == 1.0
    assert result["missing"] == []


def test_partial_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    all_syms = ["000625.SZ", "300750.SZ", "688716.SH"]
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: all_syms,
    )
    result = get_coverage("default", _make_bar_store(["000625.SZ"]), "2025-01-01", "2026-01-01")
    assert result["missing_count"] == 2
    assert "300750.SZ" in result["missing"]
    assert "688716.SH" in result["missing"]


def test_empty_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        lambda name: ["000625.SZ"],
    )
    result = get_coverage("default", _make_bar_store([]), "2025-01-01", "2026-01-01")
    assert result["coverage_rate"] == 0.0
    assert result["covered"] == []


def test_unknown_universe(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_name: str):
        raise FileNotFoundError("not found")

    monkeypatch.setattr(
        "application.market_data.coverage_service.load_universe",
        _boom,
    )
    with pytest.raises(FileNotFoundError):
        get_coverage("nonexistent", _make_bar_store([]), "2025-01-01", "2026-01-01")
