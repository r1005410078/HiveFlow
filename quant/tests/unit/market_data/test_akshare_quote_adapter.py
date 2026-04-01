import pandas as pd

from interfaces.adapters.market_data.akshare_quote_adapter import AkshareQuoteAdapter


class _FakeAkClient:
    def stock_zh_a_hist(self, symbol, period, start_date, end_date, adjust):
        assert symbol == "600519"
        assert period == "daily"
        assert start_date == "20260401"
        assert end_date == "20260401"
        assert adjust == "qfq"
        return pd.DataFrame(
            [
                {
                    "日期": "2026-04-01",
                    "开盘": 100.0,
                    "收盘": 101.0,
                    "最高": 103.0,
                    "最低": 99.0,
                    "成交量": 1000.0,
                    "成交额": 100000.0,
                }
            ]
        )

    def stock_zh_a_hist_min_em(self, symbol, period, start_date, end_date, adjust):
        assert symbol == "600519"
        assert period == "1"
        assert start_date == "2026-04-01 09:30:00"
        assert end_date == "2026-04-01 15:00:00"
        assert adjust == "qfq"
        return pd.DataFrame(
            [
                {
                    "时间": "2026-04-01 09:31:00",
                    "开盘": 100.0,
                    "收盘": 101.0,
                    "最高": 102.0,
                    "最低": 99.5,
                    "成交量": 300.0,
                    "成交额": 30100.0,
                }
            ]
        )


def test_akshare_quote_adapter_fetch_1d_maps_required_fields() -> None:
    adapter = AkshareQuoteAdapter(client=_FakeAkClient())
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1d")

    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["timeframe"] == "1d"
    assert rows[0]["bar_time"] == "2026-04-01T15:00:00+08:00"
    assert rows[0]["close"] == 101.0
    assert rows[0]["data_source"] == "akshare"


def test_akshare_quote_adapter_fetch_1m_maps_required_fields() -> None:
    adapter = AkshareQuoteAdapter(client=_FakeAkClient())
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")

    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["timeframe"] == "1m"
    assert rows[0]["bar_time"] == "2026-04-01T09:31:00+08:00"
    assert rows[0]["volume"] == 300.0
    assert rows[0]["data_source"] == "akshare"
