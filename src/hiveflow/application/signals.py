"""信号元数据与计算管线（Phase 1）。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

import pandas as pd
from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.application.repro_meta import (
    FEATURE_SET_VERSION,
    STYLE_PRESET_VERSION,
    resolve_code_version,
    stable_hash,
)
from hiveflow.domain.common import utc_now
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position


SIGNALS_BY_CATEGORY: dict[str, list[str]] = {
    "trend": [
        "golden_cross",
        "death_cross",
        "breakout_20d",
        "breakdown_20d",
        "momentum_20d",
        "macd_cross",
    ],
    "risk": [
        "max_drawdown_7d",
        "max_drawdown_30d",
        "atr_volatility_14d",
        "vol_regime_shift",
        "concentration_risk",
        "correlation_spike",
    ],
    "confirm": [
        "volume_breakout_confirm",
        "multi_timeframe_confirm",
        "signal_consensus",
        "trend_persistence",
    ],
    "regime": [
        "market_regime_label",
        "trend_strength_adx",
        "volatility_regime_label",
        "local_breadth_proxy",
    ],
    "quality": [
        "data_freshness",
        "data_completeness",
        "signal_stability",
        "confidence_score",
    ],
}

STYLE_NAMES: list[str] = [
    "Trend-Following",
    "Mean-Reversion",
    "Defensive-RiskOff",
    "Breakout-Aggressive",
]


@dataclass(frozen=True)
class SignalPipelineError(ValueError):
    """信号管线严格模式异常。"""

    context: str
    message: str
    details: dict
    hint: dict | str | None = None


def signal_keys_of(category: str | None = None) -> list[str]:
    """返回指定分类或全量信号键。"""
    if category:
        return list(SIGNALS_BY_CATEGORY.get(category, []))

    all_keys: list[str] = []
    for keys in SIGNALS_BY_CATEGORY.values():
        all_keys.extend(keys)
    return all_keys


def _fail(
    *,
    context: str,
    message: str,
    details: dict,
    hint: dict | str | None = None,
) -> SignalPipelineError:
    return SignalPipelineError(
        context=context,
        message=message,
        details=details,
        hint=hint,
    )


def _state_confidence(category: str, state: str) -> float:
    """按分类给出默认置信度。"""
    if category == "risk":
        return {"low": 0.85, "medium": 0.7, "high": 0.8}.get(state, 0.5)
    if category == "quality":
        return {"good": 0.9, "warning": 0.6, "bad": 0.35}.get(state, 0.5)
    return {"bullish": 0.85, "neutral": 0.5, "bearish": 0.85}.get(state, 0.5)


def _record(
    *,
    signal_key: str,
    category: str,
    symbol: str,
    as_of: str,
    state: str,
    value: float | str | None,
    threshold: float | str | None,
    triggered: bool,
    explanation: str,
    confidence: float | None = None,
) -> dict:
    return {
        "signal_key": signal_key,
        "category": category,
        "symbol": symbol,
        "as_of": as_of,
        "state": state,
        "value": value,
        "threshold": threshold,
        "triggered": triggered,
        "confidence": round(
            confidence if confidence is not None else _state_confidence(category, state), 4
        ),
        "explanation": explanation,
    }


def _max_drawdown(values: pd.Series) -> float:
    peak = None
    mdd = 0.0
    for value in values.tolist():
        if peak is None:
            peak = value
        peak = max(peak, value)
        if peak <= 0:
            continue
        drawdown = value / peak - 1.0
        mdd = min(mdd, drawdown)
    return float(mdd)


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = _true_range(high, low, close)
    atr = tr.rolling(period).mean()
    plus_di = 100 * (plus_dm.rolling(period).mean() / atr.replace(0, math.nan))
    minus_di = 100 * (minus_dm.rolling(period).mean() / atr.replace(0, math.nan))
    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, math.nan))
    series = dx.rolling(period).mean().dropna()
    if series.empty:
        return 0.0
    return float(series.iloc[-1])


def _quantile_rank(series: pd.Series, value: float) -> float:
    if series.empty:
        return 0.5
    return float((series <= value).sum() / len(series))


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return ordered[lo]
    frac = pos - lo
    return ordered[lo] * (1 - frac) + ordered[hi] * frac


def _load_market_context(settings: Settings) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[Position]]:
    create_all_tables(settings)
    with get_session(settings) as session:
        bars = session.exec(select(MarketBar).order_by(MarketBar.timestamp)).all()
        positions = session.exec(select(Position)).all()

    if not bars:
        raise _fail(
            context="signal.snapshot",
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "missing_signals": signal_keys_of(),
                "missing_categories": list(SIGNALS_BY_CATEGORY.keys()),
                "reason": "MarketBar is empty",
            },
            hint={"action": "sync_and_compute_signals", "suggested_sync_days": 90},
        )

    rows = [
        {
            "symbol": b.symbol.upper(),
            "timestamp": b.timestamp.astimezone(timezone.utc),
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
        }
        for b in bars
    ]
    df = pd.DataFrame(rows).sort_values(["timestamp", "symbol"])
    close = df.pivot_table(index="timestamp", columns="symbol", values="close").sort_index()
    high = df.pivot_table(index="timestamp", columns="symbol", values="high").sort_index()
    low = df.pivot_table(index="timestamp", columns="symbol", values="low").sort_index()
    volume = df.pivot_table(index="timestamp", columns="symbol", values="volume").sort_index()
    return close, high, low, volume, positions


def _leader_symbol(close: pd.DataFrame, positions: list[Position]) -> str:
    candidates = [s for s in close.columns.tolist() if s != "USDT"]
    if not candidates:
        return close.columns.tolist()[0]

    if positions:
        best = max(positions, key=lambda p: p.market_value or 0.0).symbol.upper()
        if best in candidates:
            return best
    return sorted(candidates)[0]


def pick_leader_symbol(settings: Settings | None = None) -> str:
    """从持仓和 MarketBar 中选出市值最大的资产 symbol。

    无持仓时退化为 MarketBar 中按字母排序的第一个非 USDT symbol。
    """
    close_df, _, _, _, positions = _load_market_context(settings or Settings())
    return _leader_symbol(close_df, positions)


def _autodetect_symbol(settings: Settings | None = None) -> str:
    """CLI 内部桥接函数，待 Task 9 完成后可移除。"""
    return pick_leader_symbol(settings)


def _ensure_required_samples(
    *,
    series: pd.Series,
    required: int,
    signal_key: str,
    context: str,
    symbol: str,
) -> None:
    actual = int(series.dropna().shape[0])
    if actual < required:
        raise _fail(
            context=context,
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "signal_key": signal_key,
                "symbol": symbol,
                "required_samples": required,
                "actual_samples": actual,
                "reason": "insufficient_samples",
            },
            hint={"action": "sync_and_compute_signals", "suggested_sync_days": 90},
        )


def build_signal_snapshot(
    symbol: str,
    settings: Settings | None = None,
    *,
    window_bars: int | None = None,
) -> dict:
    """计算并返回 Phase 1 聚合信号快照。"""
    app_settings = settings or Settings()
    close_df, high_df, low_df, volume_df, positions = _load_market_context(app_settings)
    if window_bars is not None and window_bars > 0:
        # 关键层信号包含 MA/MACD 等至少 40 样本要求，窗口过小时自动扩展到 40。
        scoped = max(window_bars, 40)
        close_df = close_df.tail(scoped)
        high_df = high_df.tail(scoped)
        low_df = low_df.tail(scoped)
        volume_df = volume_df.tail(scoped)

    symbol = symbol.upper()
    if symbol not in close_df.columns:
        raise _fail(
            context="signal.snapshot",
            message=f"Symbol {symbol!r} 在 MarketBar 中无数据，严格模式中断。",
            details={
                "strict_mode": True,
                "symbol": symbol,
                "available_symbols": sorted(close_df.columns.tolist()),
                "reason": "symbol_not_found",
            },
            hint={"action": "check_market_data", "run": "hiveflow market-data list"},
        )
    close = close_df[symbol].dropna()
    high = high_df[symbol].dropna()
    low = low_df[symbol].dropna()
    volume = volume_df[symbol].dropna()

    _ensure_required_samples(
        series=close,
        required=40,
        signal_key="macd_cross",
        context="signal.snapshot",
        symbol=symbol,
    )

    universe_symbols = [
        s
        for s in close_df.columns.tolist()
        if s != "USDT" and close_df[s].dropna().shape[0] >= 30
    ]
    if len(universe_symbols) < 2:
        raise _fail(
            context="signal.snapshot",
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "signal_key": "local_breadth_proxy",
                "required_samples": 30,
                "actual_symbols": len(universe_symbols),
                "reason": "insufficient_universe",
            },
            hint={"action": "sync_and_compute_signals", "suggested_sync_days": 90},
        )

    if not positions:
        raise _fail(
            context="signal.snapshot",
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "signal_key": "concentration_risk",
                "reason": "positions_empty",
            },
            hint={"action": "sync_positions_first"},
        )

    as_of = utc_now().isoformat()
    data_start = close_df.index.min().astimezone(timezone.utc).isoformat()
    data_end = close_df.index.max().astimezone(timezone.utc).isoformat()

    signals_by_key: dict[str, dict] = {}

    # ── trend ──
    fast_cur = float(close.tail(7).mean())
    slow_cur = float(close.tail(30).mean())
    fast_prev = float(close.iloc[-8:-1].mean())
    slow_prev = float(close.iloc[-31:-1].mean())
    golden = fast_prev <= slow_prev and fast_cur > slow_cur
    death = fast_prev >= slow_prev and fast_cur < slow_cur

    signals_by_key["golden_cross"] = _record(
        signal_key="golden_cross",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state="bullish" if golden else "neutral",
        value=round(fast_cur - slow_cur, 6),
        threshold=0.0,
        triggered=golden,
        explanation="MA7 上穿 MA30 判定金叉。",
    )
    signals_by_key["death_cross"] = _record(
        signal_key="death_cross",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state="bearish" if death else "neutral",
        value=round(fast_cur - slow_cur, 6),
        threshold=0.0,
        triggered=death,
        explanation="MA7 下穿 MA30 判定死叉。",
    )

    high_20 = float(high.iloc[-21:-1].max())
    low_20 = float(low.iloc[-21:-1].min())
    close_now = float(close.iloc[-1])
    breakout = close_now > high_20
    breakdown = close_now < low_20
    signals_by_key["breakout_20d"] = _record(
        signal_key="breakout_20d",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state="bullish" if breakout else "neutral",
        value=round(close_now, 6),
        threshold=round(high_20, 6),
        triggered=breakout,
        explanation="收盘价是否突破过去 20 日高点。",
    )
    signals_by_key["breakdown_20d"] = _record(
        signal_key="breakdown_20d",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state="bearish" if breakdown else "neutral",
        value=round(close_now, 6),
        threshold=round(low_20, 6),
        triggered=breakdown,
        explanation="收盘价是否跌破过去 20 日低点。",
    )

    momentum_20d = float(close.iloc[-1] / close.iloc[-21] - 1.0)
    if momentum_20d > 0.05:
        momentum_state = "bullish"
    elif momentum_20d < -0.05:
        momentum_state = "bearish"
    else:
        momentum_state = "neutral"
    signals_by_key["momentum_20d"] = _record(
        signal_key="momentum_20d",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state=momentum_state,
        value=round(momentum_20d, 6),
        threshold=0.05,
        triggered=momentum_state != "neutral",
        explanation="20 日动量阈值分层（±5%）。",
        confidence=min(1.0, max(0.3, abs(momentum_20d) / 0.1)),
    )

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    diff = ema12 - ema26
    dea = diff.ewm(span=9, adjust=False).mean()
    prev_cross = float(diff.iloc[-2] - dea.iloc[-2])
    curr_cross = float(diff.iloc[-1] - dea.iloc[-1])
    macd_state = "neutral"
    if prev_cross <= 0 < curr_cross:
        macd_state = "bullish"
    elif prev_cross >= 0 > curr_cross:
        macd_state = "bearish"
    signals_by_key["macd_cross"] = _record(
        signal_key="macd_cross",
        category="trend",
        symbol=symbol,
        as_of=as_of,
        state=macd_state,
        value=round(curr_cross, 6),
        threshold=0.0,
        triggered=macd_state != "neutral",
        explanation="DIFF 与 DEA 的当期交叉状态。",
    )

    # ── risk ──
    mdd_7d = _max_drawdown(close.tail(7))
    mdd_30d = _max_drawdown(close.tail(30))
    state_7d = "high" if mdd_7d <= -0.2 else ("medium" if mdd_7d <= -0.1 else "low")
    state_30d = "high" if mdd_30d <= -0.3 else ("medium" if mdd_30d <= -0.15 else "low")
    signals_by_key["max_drawdown_7d"] = _record(
        signal_key="max_drawdown_7d",
        category="risk",
        symbol=symbol,
        as_of=as_of,
        state=state_7d,
        value=round(mdd_7d, 6),
        threshold=-0.1,
        triggered=state_7d != "low",
        explanation="过去 7 期最大回撤分层。",
    )
    signals_by_key["max_drawdown_30d"] = _record(
        signal_key="max_drawdown_30d",
        category="risk",
        symbol=symbol,
        as_of=as_of,
        state=state_30d,
        value=round(mdd_30d, 6),
        threshold=-0.15,
        triggered=state_30d != "low",
        explanation="过去 30 期最大回撤分层。",
    )

    atr14 = float(_true_range(high, low, close).rolling(14).mean().dropna().iloc[-1])
    atr_ratio = atr14 / close_now if close_now > 0 else 0.0
    atr_state = "high" if atr_ratio > 0.05 else ("medium" if atr_ratio > 0.02 else "low")
    signals_by_key["atr_volatility_14d"] = _record(
        signal_key="atr_volatility_14d",
        category="risk",
        symbol=symbol,
        as_of=as_of,
        state=atr_state,
        value=round(atr_ratio, 6),
        threshold=0.02,
        triggered=atr_state != "low",
        explanation="ATR14 / close 波动率分层。",
    )

    ret = close.pct_change().dropna()
    rolling_vol = float(ret.tail(20).std(ddof=1)) if ret.tail(20).shape[0] >= 2 else 0.0
    baseline_vol = float(ret.std(ddof=1)) if ret.shape[0] >= 2 else 0.0
    ratio = rolling_vol / baseline_vol if baseline_vol > 0 else 1.0
    vol_shift_state = "high" if ratio >= 1.5 else ("low" if ratio <= 0.7 else "medium")
    signals_by_key["vol_regime_shift"] = _record(
        signal_key="vol_regime_shift",
        category="risk",
        symbol=symbol,
        as_of=as_of,
        state=vol_shift_state,
        value=round(ratio, 6),
        threshold=1.5,
        triggered=vol_shift_state != "medium",
        explanation="近 20 期波动率相对基线的变化倍数。",
    )

    total_mv = sum(max(p.market_value or 0.0, 0.0) for p in positions)
    if total_mv <= 0:
        raise _fail(
            context="signal.snapshot",
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "signal_key": "concentration_risk",
                "reason": "positions_total_market_value_is_zero",
            },
            hint={"action": "sync_positions_first"},
        )
    max_weight = max((max(p.market_value or 0.0, 0.0) / total_mv) for p in positions)
    concentration_state = (
        "high" if max_weight >= 0.5 else ("medium" if max_weight >= 0.3 else "low")
    )
    signals_by_key["concentration_risk"] = _record(
        signal_key="concentration_risk",
        category="risk",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=concentration_state,
        value=round(max_weight, 6),
        threshold=0.3,
        triggered=concentration_state != "low",
        explanation="组合最大单一资产权重。",
    )

    ret_df = close_df[universe_symbols].pct_change().dropna().tail(30)
    corr = ret_df.corr()
    pair_values: list[float] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            pair_values.append(float(corr.iloc[i, j]))
    avg_corr = sum(pair_values) / len(pair_values) if pair_values else 0.0
    corr_state = "high" if avg_corr >= 0.8 else ("medium" if avg_corr >= 0.6 else "low")
    signals_by_key["correlation_spike"] = _record(
        signal_key="correlation_spike",
        category="risk",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=corr_state,
        value=round(avg_corr, 6),
        threshold=0.6,
        triggered=corr_state != "low",
        explanation="资产池 30 期平均相关系数。",
    )

    # ── confirm ──
    vol_ma20 = float(volume.iloc[-21:-1].mean())
    vol_ratio = (float(volume.iloc[-1]) / vol_ma20) if vol_ma20 > 0 else 0.0
    vol_confirm = breakout and vol_ratio >= 1.5
    signals_by_key["volume_breakout_confirm"] = _record(
        signal_key="volume_breakout_confirm",
        category="confirm",
        symbol=symbol,
        as_of=as_of,
        state="bullish" if vol_confirm else "neutral",
        value=round(vol_ratio, 6),
        threshold=1.5,
        triggered=vol_confirm,
        explanation="突破同时放量（volume >= 1.5x MA20）。",
    )

    short_mom = float(close.iloc[-1] / close.iloc[-11] - 1.0)
    long_mom = float(close.iloc[-1] / close.iloc[-31] - 1.0)
    if short_mom > 0 and long_mom > 0:
        mtf_state = "bullish"
    elif short_mom < 0 and long_mom < 0:
        mtf_state = "bearish"
    else:
        mtf_state = "neutral"
    signals_by_key["multi_timeframe_confirm"] = _record(
        signal_key="multi_timeframe_confirm",
        category="confirm",
        symbol=symbol,
        as_of=as_of,
        state=mtf_state,
        value=round(short_mom - long_mom, 6),
        threshold=0.0,
        triggered=mtf_state != "neutral",
        explanation="短/长周期动量是否同向。",
    )

    trend_pool = [
        signals_by_key["golden_cross"]["state"],
        signals_by_key["death_cross"]["state"],
        signals_by_key["breakout_20d"]["state"],
        signals_by_key["breakdown_20d"]["state"],
        signals_by_key["momentum_20d"]["state"],
        signals_by_key["macd_cross"]["state"],
    ]
    bullish_ratio = sum(1 for s in trend_pool if s == "bullish") / len(trend_pool)
    bearish_ratio = sum(1 for s in trend_pool if s == "bearish") / len(trend_pool)
    if bullish_ratio >= 0.75:
        consensus_state = "bullish"
    elif bearish_ratio >= 0.75:
        consensus_state = "bearish"
    else:
        consensus_state = "neutral"
    signals_by_key["signal_consensus"] = _record(
        signal_key="signal_consensus",
        category="confirm",
        symbol=symbol,
        as_of=as_of,
        state=consensus_state,
        value=round(max(bullish_ratio, bearish_ratio), 6),
        threshold=0.75,
        triggered=consensus_state != "neutral",
        explanation="趋势核心信号同向比例。",
    )

    trend_hist: list[str] = []
    for lag in range(5, 0, -1):
        sub = close.iloc[: len(close) - lag + 1]
        ma7 = float(sub.tail(7).mean())
        ma30 = float(sub.tail(30).mean())
        if ma7 > ma30:
            trend_hist.append("bullish")
        elif ma7 < ma30:
            trend_hist.append("bearish")
        else:
            trend_hist.append("neutral")
    tail_state = trend_hist[-1]
    persistence = 1
    for idx in range(len(trend_hist) - 2, -1, -1):
        if trend_hist[idx] == tail_state and tail_state != "neutral":
            persistence += 1
        else:
            break
    persistence_state = tail_state if (tail_state != "neutral" and persistence >= 4) else "neutral"
    signals_by_key["trend_persistence"] = _record(
        signal_key="trend_persistence",
        category="confirm",
        symbol=symbol,
        as_of=as_of,
        state=persistence_state,
        value=persistence,
        threshold=4,
        triggered=persistence_state != "neutral",
        explanation="近 5 期趋势方向连续性。",
    )

    # ── regime ──
    adx14 = _adx(high, low, close, period=14)
    rolling20 = ret.rolling(20).std().dropna()
    if rolling20.empty:
        vol_quantile = 0.5
    else:
        pool = rolling20.tail(90)
        vol_quantile = _quantile_rank(pool, float(rolling20.iloc[-1]))

    if adx14 >= 25 and momentum_20d >= 0.05 and vol_quantile <= 0.8:
        regime_state = "bullish"
    elif adx14 >= 25 and momentum_20d <= -0.05 and vol_quantile >= 0.5:
        regime_state = "bearish"
    else:
        regime_state = "neutral"
    signals_by_key["market_regime_label"] = _record(
        signal_key="market_regime_label",
        category="regime",
        symbol=symbol,
        as_of=as_of,
        state=regime_state,
        value=f"adx={adx14:.2f},mom20={momentum_20d:.4f},vol_q={vol_quantile:.2f}",
        threshold="adx>=25 & momentum_20d & vol_quantile",
        triggered=regime_state != "neutral",
        explanation="冻结版 market_regime_label v1 规则。",
    )

    adx_state = "bullish" if adx14 >= 25 else "neutral"
    signals_by_key["trend_strength_adx"] = _record(
        signal_key="trend_strength_adx",
        category="regime",
        symbol=symbol,
        as_of=as_of,
        state=adx_state,
        value=round(adx14, 6),
        threshold=25.0,
        triggered=adx_state == "bullish",
        explanation="ADX14 趋势强度阈值。",
    )

    if vol_quantile >= 0.7:
        vol_regime_state = "bearish"
    elif vol_quantile <= 0.3:
        vol_regime_state = "bullish"
    else:
        vol_regime_state = "neutral"
    signals_by_key["volatility_regime_label"] = _record(
        signal_key="volatility_regime_label",
        category="regime",
        symbol=symbol,
        as_of=as_of,
        state=vol_regime_state,
        value=round(vol_quantile, 6),
        threshold="<=0.3 bullish / >=0.7 bearish",
        triggered=vol_regime_state != "neutral",
        explanation="波动率分位标签。",
    )

    up_count = 0
    for sym in universe_symbols:
        series = close_df[sym].dropna()
        if series.shape[0] < 2:
            continue
        if float(series.iloc[-1] / series.iloc[-2] - 1.0) > 0:
            up_count += 1
    up_ratio = up_count / len(universe_symbols)
    if up_ratio >= 0.7:
        breadth_state = "bullish"
    elif up_ratio <= 0.3:
        breadth_state = "bearish"
    else:
        breadth_state = "neutral"
    signals_by_key["local_breadth_proxy"] = _record(
        signal_key="local_breadth_proxy",
        category="regime",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=breadth_state,
        value=round(up_ratio, 6),
        threshold=0.7,
        triggered=breadth_state != "neutral",
        explanation="资产池上涨资产占比。",
    )

    # ── quality ──
    latest_ts = close_df.index.max().astimezone(timezone.utc)
    age_hours = (utc_now() - latest_ts).total_seconds() / 3600.0
    if age_hours <= 24:
        freshness_state = "good"
        freshness_score = 1.0
    elif age_hours <= 72:
        freshness_state = "warning"
        freshness_score = 0.5
    else:
        freshness_state = "bad"
        freshness_score = 0.0
    signals_by_key["data_freshness"] = _record(
        signal_key="data_freshness",
        category="quality",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=freshness_state,
        value=round(age_hours, 3),
        threshold=24.0,
        triggered=freshness_state != "good",
        explanation="最新行情时间戳的新鲜度。",
    )

    complete_window = close_df[universe_symbols].tail(30)
    total_cells = int(complete_window.shape[0] * complete_window.shape[1]) or 1
    missing_ratio = float(complete_window.isna().sum().sum() / total_cells)
    if missing_ratio <= 0.01:
        completeness_state = "good"
        completeness_score = 1.0
    elif missing_ratio <= 0.05:
        completeness_state = "warning"
        completeness_score = 0.5
    else:
        completeness_state = "bad"
        completeness_score = 0.0
    signals_by_key["data_completeness"] = _record(
        signal_key="data_completeness",
        category="quality",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=completeness_state,
        value=round(missing_ratio, 6),
        threshold=0.01,
        triggered=completeness_state != "good",
        explanation="窗口内缺失率。",
    )

    flip_count = 0
    for i in range(1, len(trend_hist)):
        if trend_hist[i] != trend_hist[i - 1]:
            flip_count += 1
    if flip_count <= 1:
        stability_state = "good"
        stability_score = 1.0
    elif flip_count <= 3:
        stability_state = "warning"
        stability_score = 0.5
    else:
        stability_state = "bad"
        stability_score = 0.0
    signals_by_key["signal_stability"] = _record(
        signal_key="signal_stability",
        category="quality",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=stability_state,
        value=flip_count,
        threshold=1,
        triggered=stability_state != "good",
        explanation="近 5 期趋势状态翻转次数。",
    )

    confidence_score = 0.4 * freshness_score + 0.3 * completeness_score + 0.3 * stability_score
    if confidence_score >= 0.8:
        confidence_state = "good"
    elif confidence_score >= 0.5:
        confidence_state = "warning"
    else:
        confidence_state = "bad"
    signals_by_key["confidence_score"] = _record(
        signal_key="confidence_score",
        category="quality",
        symbol="PORTFOLIO",
        as_of=as_of,
        state=confidence_state,
        value=round(confidence_score, 6),
        threshold=0.8,
        triggered=confidence_state != "good",
        explanation="freshness/completeness/stability 加权分数。",
    )

    ordered_signals = [signals_by_key[k] for k in signal_keys_of()]

    category_metrics: dict[str, dict] = {}
    for category, keys in SIGNALS_BY_CATEGORY.items():
        items = [signals_by_key[k] for k in keys]
        numeric_values = [float(i["value"]) for i in items if isinstance(i["value"], (int, float))]
        category_metrics[category] = {
            "count": len(items),
            "triggered_count": sum(1 for i in items if i["triggered"]),
            "confidence_avg": round(sum(i["confidence"] for i in items) / len(items), 6),
            "value_p25": _percentile(numeric_values, 0.25),
            "value_p50": _percentile(numeric_values, 0.5),
            "value_p75": _percentile(numeric_values, 0.75),
        }

    trend_state = "neutral"
    trend_bull = sum(1 for k in SIGNALS_BY_CATEGORY["trend"] if signals_by_key[k]["state"] == "bullish")
    trend_bear = sum(1 for k in SIGNALS_BY_CATEGORY["trend"] if signals_by_key[k]["state"] == "bearish")
    if trend_bull > trend_bear and trend_bull >= 2:
        trend_state = "bullish"
    elif trend_bear > trend_bull and trend_bear >= 2:
        trend_state = "bearish"

    risk_states = [signals_by_key[k]["state"] for k in SIGNALS_BY_CATEGORY["risk"]]
    risk_state = "high" if "high" in risk_states else ("medium" if "medium" in risk_states else "low")

    conflict_matrix: list[dict] = []
    if trend_state == "bullish" and risk_state == "high":
        conflict_matrix.append(
            {
                "conflict_key": "trend_risk_conflict",
                "lhs_category": "trend",
                "lhs_state": trend_state,
                "rhs_category": "risk",
                "rhs_state": risk_state,
                "severity": "high",
                "symbols": [symbol],
                "count": 1,
            }
        )
    if trend_state == "bearish" and risk_state == "low":
        conflict_matrix.append(
            {
                "conflict_key": "trend_risk_conflict",
                "lhs_category": "trend",
                "lhs_state": trend_state,
                "rhs_category": "risk",
                "rhs_state": risk_state,
                "severity": "medium",
                "symbols": [symbol],
                "count": 1,
            }
        )

    params_meta = {
        "trend": {"fast": 7, "slow": 30, "breakout_window": 20, "momentum_window": 20, "momentum_threshold": 0.05},
        "risk": {
            "mdd_7d": {"medium": -0.1, "high": -0.2},
            "mdd_30d": {"medium": -0.15, "high": -0.3},
            "atr_ratio": {"medium": 0.02, "high": 0.05},
            "corr": {"medium": 0.6, "high": 0.8},
        },
        "confirm": {"volume_ratio": 1.5, "consensus_ratio": 0.75, "persistence_bars": 4},
        "regime": {"adx": 25, "vol_q_low": 0.3, "vol_q_high": 0.7},
        "quality": {"freshness_h": [24, 72], "completeness": [0.01, 0.05], "weights": [0.4, 0.3, 0.3]},
    }
    symbols_for_hash = sorted(close_df.columns.tolist())

    return {
        "as_of": as_of,
        "symbol": symbol,
        "window_bars": window_bars,
        "feature_set_version": FEATURE_SET_VERSION,
        "style_preset_version": STYLE_PRESET_VERSION,
        "symbols_hash": stable_hash(symbols_for_hash),
        "params_hash": stable_hash(params_meta),
        "code_version": resolve_code_version(),
        "signals": ordered_signals,
        "category_metrics": category_metrics,
        "conflict_matrix": conflict_matrix,
        "data_window": {
            "start": data_start,
            "end": data_end,
        },
    }


def build_signal_category(category: str, settings: Settings | None = None) -> dict:
    """按分类输出信号。"""
    if category not in SIGNALS_BY_CATEGORY:
        raise _fail(
            context=f"signal.{category}",
            message="关键信号缺失，严格模式中断。",
            details={
                "strict_mode": True,
                "category": category,
                "missing_signals": [],
                "reason": "unknown_category",
            },
            hint={"action": "use_supported_category"},
        )
    leader = _autodetect_symbol(settings)
    snapshot = build_signal_snapshot(leader, settings=settings)
    return {
        "category": category,
        "as_of": snapshot["as_of"],
        "symbol": snapshot["symbol"],
        "signals": [s for s in snapshot["signals"] if s["category"] == category],
        "data_window": snapshot["data_window"],
    }
