from pathlib import Path

import pandas as pd


def persist_quotes(df: pd.DataFrame, root: Path, as_of: str):
    out = root / "data" / "raw" / f"as_of={as_of}" / "quotes.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return out
