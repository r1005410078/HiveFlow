from __future__ import annotations
import pandas as pd


def _make_bar_store(rows: list[dict]):
    class _MockBarStore:
        def list_bars(self, symbols, timeframe, start_date, end_date, limit):
            return [r for r in rows if r["symbol"] in symbols]

        def list_storage_bars(
            self,
            symbols=None,
            storage_timeframe="1m",
            start_date=None,
            end_date=None,
            limit=None,
            order="asc",
        ):
            del storage_timeframe, start_date, end_date, limit, order
            syms = symbols or []
            return [r for r in rows if r["symbol"] in syms]
    return _MockBarStore()


def test_covariance_matrix_shape():
    """Returns square DataFrame with symbols as index and columns."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B"]
    rows = []
    for i, sym in enumerate(["A", "B"]):
        for d in range(25):
            rows.append({
                "symbol": sym,
                "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00",
                "close": 100.0 + i * 10 + d * 0.5,
            })
    bar_store = _make_bar_store(rows)
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    assert isinstance(cov, pd.DataFrame)
    assert list(cov.index) == symbols
    assert list(cov.columns) == symbols
    assert cov.loc["A", "A"] > 0
    assert cov.loc["B", "B"] > 0


def test_covariance_diagonal_fallback_when_insufficient_data():
    """When a symbol has <20 valid bars, its off-diagonals are zero and diagonal is default."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B"]
    # Only 5 bars for A — below the 20-bar minimum
    rows = [
        {"symbol": "A", "bar_time": f"2026-01-{d+1:02d}T15:00:00+08:00", "close": 100.0 + d}
        for d in range(5)
    ]
    bar_store = _make_bar_store(rows)
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    # Off-diagonal involving A must be 0
    assert cov.loc["A", "B"] == 0.0
    assert cov.loc["B", "A"] == 0.0
    # Diagonal of A must be positive (default var)
    assert cov.loc["A", "A"] > 0


def test_covariance_empty_bars_returns_diagonal():
    """When bar_store returns no rows, returns diagonal matrix with default variance."""
    from application.portfolio.covariance_service import compute_covariance_matrix

    symbols = ["A", "B", "C"]
    bar_store = _make_bar_store([])
    cov = compute_covariance_matrix(symbols=symbols, as_of="2026-02-01", bar_store=bar_store)

    assert cov.shape == (3, 3)
    assert cov.loc["A", "B"] == 0.0
    for s in symbols:
        assert cov.loc[s, s] > 0
