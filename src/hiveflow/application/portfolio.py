"""跨市场组合汇总应用服务。"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.fx_rate_provider import FxRateProvider


@dataclass(frozen=True)
class PositionWithFx:
    symbol: str
    market: str
    currency: str
    quantity: float
    market_value: float
    market_value_usdt: float
    market_value_cny: float
    weight_global: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioSummary:
    positions: list[PositionWithFx]
    total_usdt: float
    total_cny: float
    fx_rate: float
    fx_source: str
    breakdown: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "positions": [p.to_dict() for p in self.positions],
            "total_usdt": self.total_usdt,
            "total_cny": self.total_cny,
            "fx_rate": self.fx_rate,
            "fx_source": self.fx_source,
            "breakdown": self.breakdown,
        }


def _convert_position(position: Position, fx_rate: float) -> PositionWithFx:
    currency = (position.currency or "USDT").upper()
    if currency == "CNY":
        value_cny = float(position.market_value)
        value_usdt = value_cny / fx_rate if fx_rate > 0 else 0.0
    else:
        value_usdt = float(position.market_value)
        value_cny = value_usdt * fx_rate

    return PositionWithFx(
        symbol=position.symbol,
        market=position.market or "crypto",
        currency=currency,
        quantity=float(position.quantity),
        market_value=float(position.market_value),
        market_value_usdt=value_usdt,
        market_value_cny=value_cny,
        weight_global=0.0,
    )


def build_portfolio_summary(settings: Settings | None = None) -> PortfolioSummary:
    """读取数据库持仓并输出统一折算后的组合视图。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    fx_rate, fx_source = FxRateProvider(app_settings).get_cny_per_usdt()
    if fx_rate <= 0:
        fx_rate = app_settings.cny_usdt_rate
        fx_source = "config_fallback"

    with get_session(app_settings) as session:
        raw_positions = session.exec(select(Position)).all()

    positions_fx = [_convert_position(p, fx_rate) for p in raw_positions]
    total_usdt = sum(p.market_value_usdt for p in positions_fx)
    total_cny = sum(p.market_value_cny for p in positions_fx)

    normalized_positions: list[PositionWithFx] = []
    for item in positions_fx:
        weight = (item.market_value_usdt / total_usdt) if total_usdt > 0 else 0.0
        normalized_positions.append(
            PositionWithFx(
                symbol=item.symbol,
                market=item.market,
                currency=item.currency,
                quantity=item.quantity,
                market_value=item.market_value,
                market_value_usdt=item.market_value_usdt,
                market_value_cny=item.market_value_cny,
                weight_global=weight,
            )
        )

    market_usdt: dict[str, float] = {}
    market_native_value: dict[str, float] = {}
    market_currency: dict[str, str] = {}
    for item in normalized_positions:
        market_usdt[item.market] = market_usdt.get(item.market, 0.0) + item.market_value_usdt
        market_native_value[item.market] = (
            market_native_value.get(item.market, 0.0)
            + (item.market_value_usdt if item.currency == "USDT" else item.market_value_cny)
        )
        market_currency[item.market] = "USDT" if item.currency == "USDT" else "CNY"

    breakdown: dict[str, dict] = {}
    for market, value_usdt in market_usdt.items():
        weight = (value_usdt / total_usdt) if total_usdt > 0 else 0.0
        breakdown[market] = {
            "weight": weight,
            "value": market_native_value.get(market, 0.0),
            "currency": market_currency.get(market, "USDT"),
        }

    normalized_positions.sort(key=lambda item: (item.market, item.symbol))
    return PortfolioSummary(
        positions=normalized_positions,
        total_usdt=total_usdt,
        total_cny=total_cny,
        fx_rate=fx_rate,
        fx_source=fx_source,
        breakdown=breakdown,
    )
