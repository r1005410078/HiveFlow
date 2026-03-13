from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置：当前仅包含数据库连接地址。"""

    database_url: str = f"sqlite:///{Path.cwd() / 'data' / 'hiveflow.db'}"
    target_template_file: str = str(Path.cwd() / "config" / "target-templates.json")

    model_config = SettingsConfigDict(
        env_prefix="HIVEFLOW_",
        extra="ignore",
    )
