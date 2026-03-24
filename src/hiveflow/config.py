from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    database_url: str = f"sqlite:///{Path.cwd() / 'data' / 'hiveflow.db'}"
    target_template_file: str = str(Path.cwd() / "config" / "target-templates.json")

    # OKX API 配置（env: HIVEFLOW_OKX_API_KEY / _SECRET / _PASSPHRASE）
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_api_passphrase: str | None = None

    # OKX Trade API（下单专用，需 Trade 权限）
    okx_trade_api_key: str | None = None
    okx_trade_api_secret: str | None = None
    okx_trade_passphrase: str | None = None

    # A 股行情数据源（env: HIVEFLOW_CN_MARKET_DATA_SOURCE）
    cn_market_data_source: str = "akshare"  # "akshare" | "tushare" | "tencent"
    # Tushare token（env: HIVEFLOW_TUSHARE_TOKEN，cn_market_data_source=tushare 时必填）
    tushare_token: str = ""
    # 货币折算回退汇率（env: HIVEFLOW_CNY_USDT_RATE，FxRateProvider 失败时使用）
    cny_usdt_rate: float = 7.25

    model_config = SettingsConfigDict(
        env_prefix="HIVEFLOW_",
        extra="ignore",
    )
