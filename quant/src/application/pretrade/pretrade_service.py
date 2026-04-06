from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import numpy as np

from application.contracts.cli_output import ok_output


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

_logger = logging.getLogger(__name__)

ETA = 0.1
DEFAULT_NOTIONAL = 1_000_000.0
LOOKBACK_TRADING_DAYS = 20
START_BUFFER_DAYS = 60
FALLBACK_ADV = 1_000_000_000.0
FALLBACK_SIGMA = 0.20
MIN_SIGMA = 0.01
MAX_PARTICIPATION_TRADABLE = 0.10
_FALLBACK_WARNING = {
    "code": "PRETRADE_USING_FALLBACK_ADV",
    "message": "bar_store unavailable; using fallback ADV=1e9 and sigma=0.20",
}


def _parse_bar_time(s: str) -> datetime:
    if "T" in s:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    return datetime.fromisoformat(s + "T00:00:00+08:00")


def _annualized_sigma_from_closes(closes: np.ndarray) -> float:
    """Daily returns std × sqrt(252), annualized."""
    if closes.size < 2:
        return FALLBACK_SIGMA
    rets = np.diff(closes) / closes[:-1]
    if rets.size >= LOOKBACK_TRADING_DAYS:
        rets = rets[-LOOKBACK_TRADING_DAYS:]
    elif rets.size < 1:
        return FALLBACK_SIGMA
    daily_std = float(np.std(rets, ddof=1)) if rets.size > 1 else float(abs(rets[0]))
    sigma = daily_std * np.sqrt(252.0)
    return max(sigma, MIN_SIGMA)


def _symbol_bars_slice(
    rows: list[dict],
    symbol: str,
    as_of: str,
) -> tuple[list[dict], bool]:
    """Last up to LOOKBACK_TRADING_DAYS daily bars for symbol on/before as_of.

    Returns (bars_asc, ok) where ok False means use fallback for this symbol.
    """
    as_of_d = date.fromisoformat(as_of)
    sym_rows = [r for r in rows if r.get("symbol") == symbol]
    parsed: list[tuple[datetime, dict]] = []
    for r in sym_rows:
        bt = r.get("bar_time")
        if bt is None:
            continue
        try:
            t = _parse_bar_time(str(bt))
        except ValueError:
            continue
        if t.date() <= as_of_d:
            parsed.append((t, r))
    if not parsed:
        return [], False
    parsed.sort(key=lambda x: x[0])
    last = parsed[-LOOKBACK_TRADING_DAYS:]
    bars = [b for _, b in last]
    return bars, True


def run_pretrade_check(
    as_of: str,
    target_weights: dict[str, float],
    bar_store=None,
    notional: float | None = None,
) -> dict:
    """L5.5 pre-trade impact / tradability estimate. Returns CLI envelope."""
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    n = float(DEFAULT_NOTIONAL if notional is None else notional)

    if not target_weights:
        return {
            "schema_version": "1.0.0",
            "command": "hf pretrade check",
            "run_id": run_id,
            "status": "error",
            "generated_at": _now_iso(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "as_of": as_of,
                "notional": n,
                "overall_tradable": False,
                "total_impact_bp": 0.0,
                "orders": [],
            },
            "warnings": [],
            "errors": [{
                "code": "TARGET_WEIGHTS_REQUIRED",
                "message": "target_weights must be a non-empty dict",
            }],
        }

    w_sum = sum(float(w) for w in target_weights.values())
    if w_sum <= 0:
        return {
            "schema_version": "1.0.0",
            "command": "hf pretrade check",
            "run_id": run_id,
            "status": "error",
            "generated_at": _now_iso(),
            "source": "system",
            "advice_only": False,
            "decision_weight": 1,
            "data": {
                "as_of": as_of,
                "notional": n,
                "overall_tradable": False,
                "total_impact_bp": 0.0,
                "orders": [],
            },
            "warnings": [],
            "errors": [{
                "code": "INVALID_WEIGHTS",
                "message": "sum of target_weights must be positive",
            }],
        }

    norm_weights = {s: float(target_weights[s]) / w_sum for s in target_weights}

    warnings: list[dict] = []
    use_fallback = False
    all_rows: list[dict] = []

    if bar_store is None:
        use_fallback = True
    else:
        start_date = (date.fromisoformat(as_of) - timedelta(days=START_BUFFER_DAYS)).isoformat()
        try:
            all_rows = bar_store.list_bars(
                symbols=list(norm_weights.keys()),
                timeframe="1d",
                start_date=start_date,
                end_date=as_of,
                limit=5000,
            )
        except Exception:
            _logger.warning("pretrade: list_bars failed, using fallback", exc_info=True)
            all_rows = []
            use_fallback = True
        if not all_rows:
            use_fallback = True

    if use_fallback:
        warnings.append(dict(_FALLBACK_WARNING))

    orders: list[dict] = []
    total_impact_weighted = 0.0

    for symbol in sorted(norm_weights.keys()):
        w = norm_weights[symbol]
        target_notional = n * w

        if use_fallback:
            adv = FALLBACK_ADV
            sigma = FALLBACK_SIGMA
        else:
            bars, ok = _symbol_bars_slice(all_rows, symbol, as_of)
            if not ok or not bars:
                if not any(x.get("code") == "PRETRADE_USING_FALLBACK_ADV" for x in warnings):
                    warnings.append(dict(_FALLBACK_WARNING))
                adv = FALLBACK_ADV
                sigma = FALLBACK_SIGMA
            else:
                closes = np.array([float(b["close"]) for b in bars], dtype=float)
                vols = np.array([float(b.get("volume", 0) or 0) for b in bars], dtype=float)
                dollar_vol = closes * vols
                adv = float(np.mean(dollar_vol)) if dollar_vol.size else 0.0
                if adv <= 0:
                    adv = FALLBACK_ADV
                    sigma = FALLBACK_SIGMA
                    if not any(x.get("code") == "PRETRADE_USING_FALLBACK_ADV" for x in warnings):
                        warnings.append(dict(_FALLBACK_WARNING))
                else:
                    raw_sigma = _annualized_sigma_from_closes(closes)
                    sigma = max(raw_sigma, MIN_SIGMA)

        participation_rate = (target_notional / adv) if adv > 0 else float("inf")
        tradable = participation_rate <= MAX_PARTICIPATION_TRADABLE
        if participation_rate > 0 and np.isfinite(participation_rate):
            impact_bp = ETA * sigma * float(np.sqrt(participation_rate)) * 10000.0
        else:
            impact_bp = 0.0

        orders.append({
            "symbol": symbol,
            "target_weight": w,
            "target_notional": target_notional,
            "adv": adv,
            "participation_rate": participation_rate if np.isfinite(participation_rate) else 0.0,
            "sigma": sigma,
            "impact_bp": impact_bp,
            "tradable": tradable,
        })
        total_impact_weighted += w * impact_bp

    overall_tradable = all(o["tradable"] for o in orders)
    data = {
        "as_of": as_of,
        "notional": n,
        "overall_tradable": overall_tradable,
        "total_impact_bp": float(total_impact_weighted),
        "orders": orders,
    }

    return ok_output(
        command="hf pretrade check",
        run_id=run_id,
        data=data,
        warnings=warnings,
    )
