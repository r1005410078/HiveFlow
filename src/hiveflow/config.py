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

    model_config = SettingsConfigDict(
        env_prefix="HIVEFLOW_",
        extra="ignore",
    )
