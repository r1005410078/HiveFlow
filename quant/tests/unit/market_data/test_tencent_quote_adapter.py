import json

from interfaces.adapters.market_data.tencent_quote_adapter import TencentQuoteAdapter


def test_tencent_quote_adapter_fetch_1d_maps_required_fields() -> None:
    def _http_get(url: str) -> str:
        assert "fqkline/get" in url
        payload = {
            "data": {
                "sh600519": {
                    "qfqday": [
                        ["2026-04-01", "100.0", "101.0", "103.0", "99.0", "1000", "100000.0"]
                    ]
                }
            }
        }
        return json.dumps(payload)

    adapter = TencentQuoteAdapter(http_get=_http_get)
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1d")

    assert len(rows) == 1
    assert rows[0]["symbol"] == "600519.SH"
    assert rows[0]["timeframe"] == "1d"
    assert rows[0]["bar_time"] == "2026-04-01T15:00:00+08:00"
    assert rows[0]["data_source"] == "tencent"


def test_tencent_quote_adapter_fetch_15m_filters_by_as_of() -> None:
    def _http_get(url: str) -> str:
        assert "mkline" in url
        assert "m15" in url
        payload = {
            "data": {
                "sh600519": {
                    "m15": [
                        ["2026-04-01 11:15:00", "100.0", "101.0", "102.0", "99.5", "300", "30100"],
                        ["2026-03-31 14:45:00", "98.0", "99.0", "99.2", "97.8", "200", "19800"],
                    ]
                }
            }
        }
        return json.dumps(payload)

    adapter = TencentQuoteAdapter(http_get=_http_get)
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="15m")

    assert len(rows) == 1
    assert rows[0]["timeframe"] == "15m"
    assert "11:15" in rows[0]["bar_time"]


def test_tencent_quote_adapter_fetch_1m_filters_by_as_of() -> None:
    def _http_get(url: str) -> str:
        assert "mkline" in url
        payload = {
            "data": {
                "sh600519": {
                    "m1": [
                        ["2026-04-01 09:31:00", "100.0", "101.0", "102.0", "99.5", "300", "30100"],
                        ["2026-03-31 14:59:00", "98.0", "99.0", "99.2", "97.8", "200", "19800"],
                    ]
                }
            }
        }
        return json.dumps(payload)

    adapter = TencentQuoteAdapter(http_get=_http_get)
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")

    assert len(rows) == 1
    assert rows[0]["bar_time"] == "2026-04-01T09:31:00+08:00"
    assert rows[0]["timeframe"] == "1m"


def test_tencent_quote_adapter_fetch_1m_skips_malformed_rows() -> None:
    def _http_get(url: str) -> str:
        assert "mkline" in url
        payload = {
            "data": {
                "sh600519": {
                    "m1": [
                        None,
                        [],
                        ["2026-04-01 09:31:00", "100.0", "101.0", "102.0", "99.5", "300", "30100"],
                    ]
                }
            }
        }
        return json.dumps(payload)

    adapter = TencentQuoteAdapter(http_get=_http_get)
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")

    assert len(rows) == 1
    assert rows[0]["bar_time"] == "2026-04-01T09:31:00+08:00"


def test_tencent_quote_adapter_fetch_1m_parses_compact_timestamp_and_non_numeric_amount() -> None:
    def _http_get(url: str) -> str:
        assert "mkline" in url
        payload = {
            "data": {
                "sh600519": {
                    "m1": [
                        ["202604010931", "100.0", "101.0", "102.0", "99.5", "300", {}],
                    ]
                }
            }
        }
        return json.dumps(payload)

    adapter = TencentQuoteAdapter(http_get=_http_get)
    rows = adapter.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")

    assert len(rows) == 1
    assert rows[0]["bar_time"] == "2026-04-01T09:31:00+08:00"
    assert rows[0]["amount"] == 0.0
