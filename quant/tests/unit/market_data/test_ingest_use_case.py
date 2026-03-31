import pandas as pd

from hiveflow.market_data.application.ingest_use_case import persist_quotes


def test_persist_quotes(tmp_path):
    """验证 L1 行情落盘成功并返回有效文件路径。"""
    df = pd.DataFrame(
        [
            {
                "symbol": "000001.SZ",
                "close": 10.0,
                "volume": 1000,
                "adj_factor": 1.0,
                "effective_date": "2026-04-01",
            }
        ]
    )
    p = persist_quotes(df, tmp_path, "2026-04-01")
    assert p.exists()
