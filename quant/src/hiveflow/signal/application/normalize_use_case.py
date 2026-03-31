import pandas as pd


def winsorize_then_zscore(s: pd.Series, lower: float = 0.05, upper: float = 0.95) -> pd.Series:
    lo, hi = s.quantile(lower), s.quantile(upper)
    clipped = s.clip(lower=lo, upper=hi)
    return (clipped - clipped.mean()) / clipped.std(ddof=0)
