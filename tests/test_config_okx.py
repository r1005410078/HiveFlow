# tests/test_config_okx.py
from hiveflow.config import Settings


def test_okx_settings_default_to_none() -> None:
    s = Settings()
    assert s.okx_api_key is None
    assert s.okx_api_secret is None
    assert s.okx_api_passphrase is None


def test_okx_settings_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "key123")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "secret456")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "pass789")
    s = Settings()
    assert s.okx_api_key == "key123"
    assert s.okx_api_secret == "secret456"
    assert s.okx_api_passphrase == "pass789"
