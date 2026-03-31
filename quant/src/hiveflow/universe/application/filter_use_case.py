import pandas as pd


def filter_universe(df: pd.DataFrame) -> pd.DataFrame:
    mask = (~df["is_st"]) & (~df["is_suspended"]) & (df["listed_days"] >= 60)
    return df.loc[mask].reset_index(drop=True)
