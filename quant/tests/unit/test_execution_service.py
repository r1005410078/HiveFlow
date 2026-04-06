"""Unit tests for L6 execution plan service."""

from __future__ import annotations

import pytest

from application.execution.execution_service import SLIPPAGE_BP, run_execution_plan


class _MockBarStore:
    def __init__(
        self,
        *,
        positions: dict[str, float] | None = None,
        rows: list[dict] | None = None,
    ) -> None:
        self.positions = dict(positions or {})
        self.rows = list(rows or [])
        self.upserts: list[tuple[str, dict[str, float]]] = []

    def get_positions_snapshot(self, as_of: str) -> dict[str, float]:
        del as_of
        return dict(self.positions)

    def list_bars(self, **kwargs: object) -> list[dict]:
        del kwargs
        return self.rows

    def upsert_positions_for_as_of(self, as_of: str, notionals: dict[str, float]) -> None:
        self.upserts.append((as_of, dict(notionals)))


def _bar_row(symbol: str, day: str, close: float) -> dict:
    return {
        "symbol": symbol,
        "timeframe": "1d",
        "bar_time": f"{day}T15:00:00+08:00",
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": 1.0,
        "amount": close,
        "adj_factor": 1.0,
        "data_source": "test",
    }


def test_open_long_buy_quantity_and_limit() -> None:
    sym = "600519.SH"
    store = _MockBarStore(
        rows=[_bar_row(sym, "2026-04-01", 1000.0)],
    )
    pretrade = {
        "orders": [{"symbol": sym, "impact_bp": 2.1, "target_weight": 1.0}],
    }
    out = run_execution_plan(
        "2026-04-01",
        {sym: 1.0},
        pretrade=pretrade,
        bar_store=store,
        notional=120_000.0,
    )
    assert out["status"] == "ok"
    assert out["command"] == "hf execution plan"
    orders = out["data"]["orders"]
    assert len(orders) == 1
    o = orders[0]
    assert o["action"] == "open_long"
    assert o["direction"] == "buy"
    assert o["quantity"] == 100
    assert o["close_price"] == 1000.0
    assert o["limit_price"] == pytest.approx(1000.0 * (1 + SLIPPAGE_BP / 10000.0))
    assert o["impact_bp"] == 2.1
    assert store.upserts, "positions should persist"


def test_add_long() -> None:
    sym = "600519.SH"
    store = _MockBarStore(
        positions={sym: 50_000.0},
        rows=[_bar_row(sym, "2026-04-01", 100.0)],
    )
    out = run_execution_plan(
        "2026-04-01",
        {sym: 1.0},
        pretrade={"orders": [{"symbol": sym, "impact_bp": 1.0}]},
        bar_store=store,
        notional=100_000.0,
    )
    acts = [o["action"] for o in out["data"]["orders"]]
    assert "add_long" in acts


def test_reduce_long_sell() -> None:
    sym = "600519.SH"
    other = "000001.SZ"
    store = _MockBarStore(
        positions={sym: 80_000.0},
        rows=[
            _bar_row(sym, "2026-04-01", 100.0),
            _bar_row(other, "2026-04-01", 10.0),
        ],
    )
    out = run_execution_plan(
        "2026-04-01",
        {sym: 0.5, other: 0.5},
        pretrade={
            "orders": [
                {"symbol": sym, "impact_bp": 1.0},
                {"symbol": other, "impact_bp": 1.0},
            ],
        },
        bar_store=store,
        notional=100_000.0,
    )
    o = next(x for x in out["data"]["orders"] if x["symbol"] == sym)
    assert o["action"] == "reduce_long"
    assert o["direction"] == "sell"


def test_close_long_when_target_zero() -> None:
    sym = "600519.SH"
    other = "000001.SZ"
    store = _MockBarStore(
        positions={sym: 50_000.0},
        rows=[
            _bar_row(sym, "2026-04-01", 50.0),
            _bar_row(other, "2026-04-01", 10.0),
        ],
    )
    out = run_execution_plan(
        "2026-04-01",
        {other: 1.0},
        pretrade={"orders": []},
        bar_store=store,
        notional=100_000.0,
    )
    o = next(x for x in out["data"]["orders"] if x["symbol"] == sym)
    assert o["action"] == "close_long"
    assert o["direction"] == "sell"


def test_bar_store_none_warning_and_null_prices() -> None:
    sym = "600519.SH"
    out = run_execution_plan(
        "2026-04-01",
        {sym: 1.0},
        pretrade=None,
        bar_store=None,
        notional=1_000_000.0,
    )
    assert out["status"] == "ok"
    assert any(w["code"] == "EXECUTION_USING_NO_PRICE" for w in out["warnings"])
    assert out["data"]["orders"]
    o = out["data"]["orders"][0]
    assert o["close_price"] is None
    assert o["quantity"] is None
    assert o["limit_price"] is None


def test_skip_small_delta() -> None:
    sym = "600519.SH"
    store = _MockBarStore(
        positions={sym: 100_000.0},
        rows=[_bar_row(sym, "2026-04-01", 100.0)],
    )
    out = run_execution_plan(
        "2026-04-01",
        {sym: 1.0},
        pretrade={"orders": [{"symbol": sym, "impact_bp": 0.0}]},
        bar_store=store,
        notional=100_000.0 + 50.0,
    )
    assert out["data"]["orders"] == []


def test_estimated_total_cost_bp_slippage_only_when_no_impact() -> None:
    sym = "A.SH"
    store = _MockBarStore(rows=[_bar_row(sym, "2026-04-01", 10.0)])
    out = run_execution_plan(
        "2026-04-01",
        {sym: 1.0},
        pretrade=None,
        bar_store=store,
        notional=10_000.0,
    )
    assert out["data"]["estimated_total_cost_bp"] == pytest.approx(float(SLIPPAGE_BP))


def test_invalid_weights_error() -> None:
    out = run_execution_plan("2026-04-01", {"X": -1.0, "Y": -1.0}, bar_store=None)
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "INVALID_WEIGHTS"


def test_empty_target_weights_error() -> None:
    out = run_execution_plan("2026-04-01", {}, bar_store=None)
    assert out["status"] == "error"
    assert out["errors"][0]["code"] == "TARGET_WEIGHTS_REQUIRED"


def test_accepts_target_weights_list() -> None:
    sym = "600519.SH"
    store = _MockBarStore(rows=[_bar_row(sym, "2026-04-01", 1000.0)])
    out = run_execution_plan(
        "2026-04-01",
        [{"symbol": sym, "weight": 1.0}],
        bar_store=store,
        notional=100_000.0,
    )
    assert out["status"] == "ok"
    assert out["data"]["orders"]
