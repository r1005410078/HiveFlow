from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from application.contracts.cli_output import ok_output

_logger = logging.getLogger(__name__)

SLIPPAGE_BP = 5
MIN_REL_DELTA = 0.01
EPS_CURRENT_NOTIONAL = 1e-9
CLOSE_LONG_MAX_TARGET = 1.0  # CNY — treat as flat for action labeling


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_bar_day(s: str) -> date:
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    return date.fromisoformat(s)


def _weights_dict(target_weights: dict[str, float] | list[dict]) -> dict[str, float]:
    if isinstance(target_weights, list):
        return {str(r["symbol"]): float(r["weight"]) for r in target_weights}
    return {str(k): float(v) for k, v in target_weights.items()}


def _latest_closes(bar_store: object, symbols: list[str], as_of: str) -> dict[str, float]:
    if bar_store is None or not symbols:
        return {}
    try:
        end_d = date.fromisoformat(as_of)
        start_d = end_d - timedelta(days=120)
        rows = bar_store.list_bars(
            symbols=symbols,
            timeframe="1d",
            start_date=start_d.isoformat(),
            end_date=as_of,
            limit=8000,
        )
    except Exception:
        _logger.warning("execution: list_bars failed", exc_info=True)
        return {}
    as_of_d = date.fromisoformat(as_of)
    best: dict[str, tuple[date, float]] = {}
    for row in rows:
        sym = row.get("symbol")
        if sym not in symbols:
            continue
        bt = row.get("bar_time")
        if not bt:
            continue
        try:
            bd = _parse_bar_day(str(bt))
        except ValueError:
            continue
        if bd > as_of_d:
            continue
        close = float(row["close"])
        prev = best.get(sym)
        if prev is None or bd > prev[0]:
            best[sym] = (bd, close)
    return {s: best[s][1] for s in best}


def _impact_by_symbol(pretrade: dict | None) -> dict[str, float | None]:
    if not pretrade:
        return {}
    orders = pretrade.get("orders") or []
    out: dict[str, float | None] = {}
    for o in orders:
        sym = o.get("symbol")
        if not sym:
            continue
        ib = o.get("impact_bp")
        out[str(sym)] = float(ib) if ib is not None else None
    return out


def _action_direction(current_notional: float, target_notional: float, delta: float) -> tuple[str, str]:
    if delta >= 0:
        if current_notional <= EPS_CURRENT_NOTIONAL:
            return "open_long", "buy"
        return "add_long", "buy"
    if target_notional <= CLOSE_LONG_MAX_TARGET:
        return "close_long", "sell"
    return "reduce_long", "sell"


def run_execution_plan(
    as_of: str,
    target_weights: dict[str, float] | list[dict],
    *,
    pretrade: dict | None = None,
    bar_store: object | None = None,
    notional: float = 1_000_000.0,
) -> dict:
    run_id = f"exec_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    w_map = _weights_dict(target_weights)
    if not w_map:
        return {
            "schema_version": "1.0.0",
            "command": "hf execution plan",
            "run_id": run_id,
            "status": "error",
            "generated_at": _now_iso(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "as_of": as_of,
                "slippage_bp": SLIPPAGE_BP,
                "estimated_total_cost_bp": 0.0,
                "orders": [],
            },
            "warnings": [],
            "errors": [{
                "code": "TARGET_WEIGHTS_REQUIRED",
                "message": "target_weights must be non-empty",
            }],
        }

    w_sum = sum(w_map.values())
    if w_sum <= 0:
        return {
            "schema_version": "1.0.0",
            "command": "hf execution plan",
            "run_id": run_id,
            "status": "error",
            "generated_at": _now_iso(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "as_of": as_of,
                "slippage_bp": SLIPPAGE_BP,
                "estimated_total_cost_bp": 0.0,
                "orders": [],
            },
            "warnings": [],
            "errors": [{
                "code": "INVALID_WEIGHTS",
                "message": "sum of target_weights must be positive",
            }],
        }

    norm_w = {s: w_map[s] / w_sum for s in w_map}

    current: dict[str, float] = {}
    if bar_store is not None and hasattr(bar_store, "get_positions_snapshot"):
        try:
            current = dict(bar_store.get_positions_snapshot(as_of))
        except Exception:
            _logger.warning("execution: get_positions_snapshot failed", exc_info=True)
            current = {}

    impact_map = _impact_by_symbol(pretrade)

    estimated_total_cost_bp = 0.0
    for sym, w in norm_w.items():
        imp = impact_map.get(sym)
        extra = float(imp) if imp is not None else 0.0
        estimated_total_cost_bp += w * (SLIPPAGE_BP + extra)

    all_syms = sorted(set(norm_w.keys()) | {s for s, v in current.items() if v > 1e-9})
    closes = _latest_closes(bar_store, all_syms, as_of)

    orders: list[dict] = []
    had_no_price = False

    for sym in all_syms:
        w = norm_w.get(sym, 0.0)
        target_notional = w * notional
        cur_n = float(current.get(sym, 0.0))
        delta = target_notional - cur_n
        denom = max(cur_n, 1.0)
        if abs(delta) / denom < MIN_REL_DELTA:
            continue

        action, direction = _action_direction(cur_n, target_notional, delta)
        close_p = closes.get(sym)
        imp_out = impact_map.get(sym)

        if close_p is not None and close_p > 0:
            qty = int(math.floor(abs(delta) / close_p / 100.0) * 100)
            slip = SLIPPAGE_BP / 10000.0
            if direction == "buy":
                lim = round(close_p * (1 + slip), 2)
            else:
                lim = round(close_p * (1 - slip), 2)
            if qty <= 0:
                continue
        else:
            had_no_price = True
            close_p = None
            qty = None
            lim = None

        orders.append({
            "symbol": sym,
            "direction": direction,
            "action": action,
            "quantity": qty,
            "target_notional": target_notional,
            "current_notional": cur_n,
            "close_price": close_p,
            "limit_price": lim,
            "order_type": "limit",
            "validity": "day",
            "impact_bp": imp_out,
        })

    warnings: list[dict] = []
    if had_no_price:
        warnings.append({
            "code": "EXECUTION_USING_NO_PRICE",
            "message": "bar_store unavailable; close_price/quantity/limit_price set to null",
        })

    notionals_to_save = {s: n for s in all_syms if (n := norm_w.get(s, 0.0) * notional) > 0}
    if bar_store is not None and hasattr(bar_store, "upsert_positions_for_as_of"):
        try:
            bar_store.upsert_positions_for_as_of(as_of, notionals_to_save)
        except Exception:
            _logger.warning("execution: upsert_positions_for_as_of failed", exc_info=True)

    return ok_output(
        command="hf execution plan",
        run_id=run_id,
        data={
            "as_of": as_of,
            "slippage_bp": SLIPPAGE_BP,
            "estimated_total_cost_bp": round(estimated_total_cost_bp, 4),
            "orders": orders,
        },
        warnings=warnings,
    )
