from __future__ import annotations


ALLOWED_TIMEFRAMES = {"1d", "1m"}


def validate_timeframe(timeframe: str) -> str:
    if timeframe not in ALLOWED_TIMEFRAMES:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    return timeframe

