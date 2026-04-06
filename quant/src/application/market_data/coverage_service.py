from __future__ import annotations

from application.market_data.universe_symbols import norm_exchange_symbol
from domain.universe.universe_loader import load_universe

# Large universes may need pagination via after_symbol; current pools are << this cap.
_COVERAGE_DB_SYMBOL_PAGE_LIMIT = 10_000


def get_coverage(
    universe: str,
    bar_store,
    start_date: str,
    end_date: str,
    min_bars: int = 1,
) -> dict:
    """Compare universe symbols against DB bar coverage (1d storage timeframe)."""
    raw_lines = load_universe(universe)
    universe_symbols = sorted(
        {
            norm_exchange_symbol(line)
            for line in raw_lines
            if line and str(line).strip()
        }
    )
    if not universe_symbols:
        raise ValueError(f"universe {universe} has no symbols")

    syms, _has_more = bar_store.list_symbols_with_min_bars_in_window(
        storage_timeframe="1d",
        start_date=start_date,
        end_date=end_date,
        min_bars=min_bars,
        after_symbol=None,
        limit=_COVERAGE_DB_SYMBOL_PAGE_LIMIT,
    )
    db_covered = set(syms)

    universe_set = set(universe_symbols)
    covered = sorted(universe_set & db_covered)
    missing = sorted(universe_set - db_covered)

    n = len(universe_symbols)
    return {
        "universe": universe,
        "start_date": start_date,
        "end_date": end_date,
        "min_bars": min_bars,
        "universe_size": n,
        "covered_count": len(covered),
        "missing_count": len(missing),
        "coverage_rate": round(len(covered) / n, 4) if n else 0.0,
        "covered": covered,
        "missing": missing,
    }
