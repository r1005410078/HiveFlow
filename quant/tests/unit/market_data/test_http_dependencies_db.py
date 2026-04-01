from interfaces.adapters.market_data.timescale_bar_store import TimescaleBarStore
from interfaces.http import dependencies as deps


def test_build_bar_store_falls_back_to_in_memory_without_db_env(monkeypatch) -> None:
    monkeypatch.delenv("HF_DB_DSN", raising=False)
    monkeypatch.delenv("HF_DB_HOST", raising=False)
    monkeypatch.delenv("POSTGRES_HOST", raising=False)
    store = deps._build_bar_store()
    assert store.__class__.__name__ == "_InMemoryBarStore"


def test_build_bar_store_uses_timescale_when_db_env_present(monkeypatch) -> None:
    class _DummyConn:
        pass

    dummy = _DummyConn()
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")
    monkeypatch.setattr(deps, "open_db_connection_from_env", lambda: dummy)

    store = deps._build_bar_store()
    assert isinstance(store, TimescaleBarStore)
    assert store._conn is dummy
