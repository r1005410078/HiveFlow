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


ALGOS_PAYLOAD = {
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

POSITIONS_BTC = {"code": "0", "data": [{"baseSz": "0.005", "quoteSz": "100"}]}
POSITIONS_ETH = {"code": "0", "data": [{"baseSz": "0.1", "quoteSz": "50"}]}
POSITIONS_EMPTY = {"code": "0", "data": []}


def test_fetch_grid_positions_returns_spot_grids() -> None:
    # 3 次调用：1 次 orders-algo-pending，2 次 grid/positions（每个 algo 一次）
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = [
            _resp(ALGOS_PAYLOAD),
            _resp(POSITIONS_BTC),
            _resp(POSITIONS_ETH),
        ]
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()

    assert len(positions) == 2
    assert positions[0].symbol == "BTC"
    assert positions[0].grid_id == "001"
    assert positions[0].inst_id == "BTC-USDT"
    assert positions[0].base_quantity == 0.005
    assert positions[0].quote_quantity == 100.0
    assert positions[0].state == "running"
    assert positions[1].symbol == "ETH"
    assert positions[1].grid_id == "002"


def test_fetch_grid_positions_falls_back_to_algo_sz_when_positions_empty() -> None:
    """grid/positions 返回空时，从 algo 层的 baseSz/quoteSz 回退。"""
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = [
            _resp(ALGOS_PAYLOAD),
            _resp(POSITIONS_EMPTY),
            _resp(POSITIONS_EMPTY),
        ]
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()

    assert len(positions) == 2
    assert positions[0].base_quantity == 0.005
    assert positions[0].quote_quantity == 100.0


def test_fetch_grid_positions_contract_grid_uses_investment() -> None:
    """合约网格用 investment 字段作为 USDT，base_quantity 为 0。"""
    swap_algos = {
        "code": "0",
        "data": [
            {
                "algoId": "swap001",
                "instId": "ETH-USDT-SWAP",
                "instType": "SWAP",
                "baseSz": "",
                "quoteSz": "",
                "investment": "352.03",
                "sz": "352.03",
                "state": "running",
            }
        ],
    }
    spot_empty = {"code": "0", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.side_effect = [
            _resp(spot_empty),           # SPOT orders-algo-pending → 空
            _resp(swap_algos),           # SWAP orders-algo-pending → 1条
            _resp({"code": "0", "data": []}),  # SWAP grid/positions → 空（走 investment 回退）
        ]
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "ETH"
    assert positions[0].inst_type == "SWAP"
    assert positions[0].base_quantity == 0.0
    assert positions[0].quote_quantity == 352.03


def test_fetch_grid_positions_returns_empty_when_none() -> None:
    payload = {"code": "0", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()
    assert positions == []
