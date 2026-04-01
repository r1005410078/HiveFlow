from fastapi import FastAPI

from interfaces.http.routes_daily_run import router as daily_router
from interfaces.http.routes_market_data import router as market_data_router


def create_app() -> FastAPI:
    app = FastAPI(title="HiveFlow Quant Service", version="0.1.0")
    app.include_router(daily_router)
    app.include_router(market_data_router)
    return app
