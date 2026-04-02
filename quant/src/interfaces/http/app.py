from fastapi import FastAPI

from interfaces.http.routes_daily_run import router as daily_router
from interfaces.http.routes_factor_optimization import router as factor_optimization_router
from interfaces.http.routes_market_data import router as market_data_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="HiveFlow Quant Service",
        version="0.1.0",
        description=(
            "HiveFlow 量化核心服务 API。\n\n"
            "提供日频策略流水线（因子计算、候选排名、执行计划）"
            "与行情数据管理（同步、查询、K 线）两大模块。\n\n"
            "所有响应遵循统一 CLI Output Schema v1.0.0，"
            "字段含义参见 `docs/CLI_OUTPUT_SCHEMA.json`。"
        ),
        contact={"name": "HiveFlow", "email": ""},
        license_info={"name": "Private"},
    )
    app.include_router(daily_router)
    app.include_router(factor_optimization_router)
    app.include_router(market_data_router)
    return app
