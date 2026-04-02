from __future__ import annotations


_FACTOR_VERSION = "l2-basic-v1.1"
_FACTOR_NAMES = (
    "momentum_20",
    "inv_volatility_20",
    "turnover_rate",
    "max_drawdown_60",
    "trend_stability_20",
    "relative_strength_vs_index",
)


def _base_seed(symbol: str) -> int:
    # Keep L2 MVP deterministic without introducing random data.
    return int(symbol.split(".", 1)[0]) % 1000


def _factor_values_for_symbol(symbol: str) -> dict[str, float]:
    seed = _base_seed(symbol)
    momentum = round(0.01 + (seed % 50) / 1000, 6)
    inv_volatility = round(1.0 + (seed % 30) / 10.0, 6)
    turnover_rate = round(0.005 + (seed % 20) / 1000, 6)
    # Encode lower drawdown as a higher score-compatible value.
    max_drawdown_60 = round(0.65 + (seed % 30) / 100, 6)
    trend_stability_20 = round(0.5 + (seed % 40) / 100, 6)
    relative_strength_vs_index = round(0.9 + (seed % 35) / 100, 6)
    return {
        "momentum_20": momentum,
        "inv_volatility_20": inv_volatility,
        "turnover_rate": turnover_rate,
        "max_drawdown_60": max_drawdown_60,
        "trend_stability_20": trend_stability_20,
        "relative_strength_vs_index": relative_strength_vs_index,
    }


def compute_basic_factor_snapshot(as_of: str, symbols: list[str]) -> dict:
    rows: list[dict] = []
    for symbol in symbols:
        values = _factor_values_for_symbol(symbol)
        for factor_name, raw_value in values.items():
            rows.append(
                {
                    "as_of": as_of,
                    "symbol": symbol,
                    "factor_name": factor_name,
                    "factor_version": _FACTOR_VERSION,
                    "raw_value": raw_value,
                }
            )

    coverage_rate = 0.0
    if symbols:
        coverage_rate = round(len(rows) / (len(symbols) * len(_FACTOR_NAMES)), 4)

    return {
        "factor_version": _FACTOR_VERSION,
        "factor_names": list(_FACTOR_NAMES),
        "coverage_rate": coverage_rate,
        "rows": rows,
    }
