import pandas as pd


def compute_basic_factors(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["momentum_20"] = out["close"].pct_change(20)
    out["inv_volatility_20"] = 1.0 / out["close"].pct_change().rolling(20).std()
    out["turnover_rate"] = out["turnover"]
    return out
