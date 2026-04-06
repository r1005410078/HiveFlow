from __future__ import annotations

from datetime import date, timedelta


def _bars_for_symbol(
    symbol: str,
    as_of: str,
    *,
    n_days: int = 25,
    base_close: float = 100.0,
    daily_return: float = 0.002,
    volume: float = 5_000_000.0,
) -> list[dict]:
    """Ascending daily bars ending on as_of (inclusive)."""
    end = date.fromisoformat(as_of)
    rows: list[dict] = []
    price = base_close
    for i in range(n_days):
        d = end - timedelta(days=(n_days - 1 - i))
        rows.append({
            "symbol": symbol,
            "bar_time": f"{d.isoformat()}T15:00:00+08:00",
            "close": price,
            "volume": volume,
        })
        price *= 1.0 + daily_return
    return rows


def _make_bar_store(rows: list[dict]):
    class _Mock:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

    return _Mock()


def test_all_tradable_positive_total_impact():
    from application.pretrade.pretrade_service import run_pretrade_check

    s1, s2 = "600519.SH", "300750.SZ"
    rows = _bars_for_symbol(s1, "2026-02-15") + _bars_for_symbol(s2, "2026-02-15")
    store = _make_bar_store(rows)
    weights = {s1: 0.6, s2: 0.4}
    out = run_pretrade_check("2026-02-15", weights, bar_store=store, notional=1_000_000.0)
    assert out["status"] == "ok"
    d = out["data"]
    assert d["overall_tradable"] is True
    assert d["total_impact_bp"] > 0
    assert len(d["orders"]) == 2
    assert {o["symbol"] for o in d["orders"]} == {s1, s2}
    assert out["warnings"] == []


def test_participation_exceeds_threshold_not_tradable():
    from application.pretrade.pretrade_service import run_pretrade_check

    s1, s2 = "600519.SH", "300750.SZ"
    rows = _bars_for_symbol(s1, "2026-02-15", volume=5_000_000.0)
    rows += _bars_for_symbol(
        s2,
        "2026-02-15",
        base_close=1.0,
        daily_return=0.0,
        volume=1.0,
    )
    store = _make_bar_store(rows)
    weights = {s1: 0.5, s2: 0.5}
    out = run_pretrade_check("2026-02-15", weights, bar_store=store, notional=1_000_000.0)
    assert out["status"] == "ok"
    d = out["data"]
    tiny = next(o for o in d["orders"] if o["symbol"] == s2)
    assert tiny["tradable"] is False
    assert d["overall_tradable"] is False


def test_bar_store_none_uses_fallback_and_warning():
    from application.pretrade.pretrade_service import run_pretrade_check

    out = run_pretrade_check(
        "2026-02-15",
        {"600519.SH": 1.0},
        bar_store=None,
        notional=1_000_000.0,
    )
    assert out["status"] == "ok"
    assert any(w.get("code") == "PRETRADE_USING_FALLBACK_ADV" for w in out["warnings"])
    o = out["data"]["orders"][0]
    assert o["adv"] == 1_000_000_000.0
    assert o["sigma"] == 0.20


def test_empty_list_bars_uses_fallback():
    from application.pretrade.pretrade_service import run_pretrade_check

    class Empty:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return []

    out = run_pretrade_check(
        "2026-02-15",
        {"600519.SH": 1.0},
        bar_store=Empty(),
        notional=1_000_000.0,
    )
    assert out["status"] == "ok"
    assert any(w.get("code") == "PRETRADE_USING_FALLBACK_ADV" for w in out["warnings"])


def test_sigma_clamped_to_minimum():
    from application.pretrade.pretrade_service import run_pretrade_check

    sym = "600519.SH"
    end = date.fromisoformat("2026-02-15")
    rows = []
    price = 100.0
    for i in range(25):
        d = end - timedelta(days=(24 - i))
        price += 1e-6
        rows.append({
            "symbol": sym,
            "bar_time": f"{d.isoformat()}T15:00:00+08:00",
            "close": price,
            "volume": 1e6,
        })
    store = _make_bar_store(rows)
    out = run_pretrade_check("2026-02-15", {sym: 1.0}, bar_store=store)
    o = out["data"]["orders"][0]
    assert o["sigma"] >= 0.01
    assert o["impact_bp"] >= 0.0
