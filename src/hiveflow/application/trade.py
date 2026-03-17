# src/hiveflow/application/trade.py
"""OKX 现货交易执行用例。"""
from __future__ import annotations
from dataclasses import dataclass
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxTicker


@dataclass(frozen=True)
class TradeOrder:
    symbol: str
    action: str   # buy / sell
    usdt: float


@dataclass
class TradeResult:
    order: TradeOrder
    order_id: str
    success: bool
    error_msg: str = ""


def execute_trades(
    orders: list[TradeOrder],
    api_key: str,
    api_secret: str,
    passphrase: str,
) -> list[TradeResult]:
    """逐个下单，不中断——调用方决定如何处理部分失败。"""
    provider = OkxProvider(api_key=api_key, api_secret=api_secret, passphrase=passphrase)

    # 为卖单预先获取当前价格
    sell_symbols = [o.symbol for o in orders if o.action == "sell"]
    price_map: dict[str, float] = {}
    if sell_symbols:
        inst_ids = [f"{s}-USDT" for s in sell_symbols]
        tickers: list[OkxTicker] = provider.fetch_tickers(inst_ids)
        price_map = {t.symbol: t.last for t in tickers}

    results = []
    for order in orders:
        inst_id = f"{order.symbol}-USDT"
        current_price = price_map.get(order.symbol)
        okx_result = provider.place_market_order(
            inst_id=inst_id,
            side=order.action,
            usdt_amount=order.usdt,
            current_price=current_price,
        )
        results.append(TradeResult(
            order=order,
            order_id=okx_result.order_id,
            success=okx_result.success,
            error_msg=okx_result.error_msg,
        ))
    return results
