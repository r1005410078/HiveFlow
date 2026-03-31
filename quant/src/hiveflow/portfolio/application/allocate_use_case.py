import pandas as pd


def allocate_weights(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    total = out["signal"].clip(lower=0).sum()
    out["target_weight"] = (out["signal"].clip(lower=0) / total) if total > 0 else (1 / len(out))
    return out[["symbol", "target_weight"]]
