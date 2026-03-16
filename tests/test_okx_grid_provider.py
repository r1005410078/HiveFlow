# tests/test_okx_grid_provider.py
import json
from unittest.mock import MagicMock, patch
import pytest
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxGridPosition


def _resp(body: dict) -> MagicMock:
    r = MagicMock()
    r.status = 200
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


def test_fetch_grid_positions_returns_spot_grids() -> None:
    payload = {
        "code": "0",
        "data": [
            {
                "algoId": "001",
                "instId": "BTC-USDT",
                "instType": "SPOT",
                "baseSz": "0.005",
                "quoteSz": "100",
                "state": "running",
            },
            {
                "algoId": "002",
                "instId": "ETH-USDT",
                "instType": "SPOT",
                "baseSz": "0.1",
                "quoteSz": "50",
                "state": "running",
            },
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()
    assert len(positions) == 2
    assert positions[0].symbol == "BTC"
    assert positions[0].grid_id == "001"
    assert positions[0].inst_id == "BTC-USDT"
    assert positions[0].base_quantity == 0.005
    assert positions[0].quote_quantity == 100.0
    assert positions[0].state == "running"


def test_fetch_grid_positions_returns_empty_when_none() -> None:
    payload = {"code": "0", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()
    assert positions == []
