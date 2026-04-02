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


def test_build_bar_store_raises_http_503_when_db_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")

    def _boom():
        raise RuntimeError("db connection refused")

    monkeypatch.setattr(deps, "open_db_connection_from_env", _boom)

    try:
        deps._build_bar_store()
    except Exception as exc:
        from fastapi import HTTPException

        assert isinstance(exc, HTTPException)
        assert exc.status_code == 503
        assert exc.detail["code"] == "MARKET_DATA_DB_UNAVAILABLE"
    else:
        raise AssertionError("expected HTTPException(503)")


def test_build_quote_repo_uses_akshare_when_tencent_fails(monkeypatch) -> None:
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")

    class _DummyRepo:
        pass

    dummy = _DummyRepo()
    monkeypatch.setattr(deps, "TencentQuoteAdapter", lambda: (_ for _ in ()).throw(RuntimeError("tencent down")))
    monkeypatch.setattr(deps, "AkshareQuoteAdapter", lambda: dummy)

    repo = deps._build_quote_repo()
    assert repo is dummy


def test_build_quote_repo_uses_tencent_first_when_db_env_present(monkeypatch) -> None:
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")

    class _DummyRepo:
        pass

    dummy = _DummyRepo()
    monkeypatch.setattr(deps, "TencentQuoteAdapter", lambda: dummy)
    monkeypatch.setattr(deps, "AkshareQuoteAdapter", lambda: None)

    repo = deps._build_quote_repo()
    assert isinstance(repo, deps._FallbackQuoteRepo)


def test_build_quote_repo_falls_back_to_akshare_when_tencent_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")

    class _DummyRepo:
        pass

    dummy = _DummyRepo()

    def _tencent_boom():
        raise RuntimeError("tencent source unavailable")

    monkeypatch.setattr(deps, "TencentQuoteAdapter", _tencent_boom)
    monkeypatch.setattr(deps, "AkshareQuoteAdapter", lambda: dummy)

    repo = deps._build_quote_repo()
    assert repo is dummy


def test_fallback_quote_repo_uses_secondary_when_primary_returns_empty() -> None:
    class _Primary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            return []

    class _Secondary:
        def fetch(self, symbols, as_of, timeframe):
            del as_of, timeframe
            return [{"symbol": symbols[0]}]

    repo = deps._FallbackQuoteRepo(primary=_Primary(), secondary=_Secondary())
    out = repo.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1d")
    assert len(out) == 1
    assert out[0]["symbol"] == "600519.SH"


def test_fallback_quote_repo_uses_secondary_when_primary_raises() -> None:
    class _Primary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            raise TypeError("'NoneType' object is not subscriptable")

    class _Secondary:
        def fetch(self, symbols, as_of, timeframe):
            del as_of, timeframe
            return [{"symbol": symbols[0]}]

    repo = deps._FallbackQuoteRepo(primary=_Primary(), secondary=_Secondary())
    out = repo.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")
    assert len(out) == 1
    assert out[0]["symbol"] == "600519.SH"


def test_fallback_quote_repo_raises_runtime_error_when_both_sources_fail() -> None:
    class _Primary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            raise RuntimeError("primary down")

    class _Secondary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            raise RuntimeError("secondary down")

    repo = deps._FallbackQuoteRepo(primary=_Primary(), secondary=_Secondary())
    try:
        repo.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")
    except RuntimeError as exc:
        assert "both market data sources failed" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_fallback_quote_repo_returns_empty_when_both_sources_return_empty() -> None:
    class _Primary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            return []

    class _Secondary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            return []

    repo = deps._FallbackQuoteRepo(primary=_Primary(), secondary=_Secondary())
    out = repo.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")
    assert out == []


def test_build_quote_repo_raises_http_503_when_all_sources_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("HF_DB_DSN", "postgresql://u:p@localhost:5432/hiveflow")

    def _boom():
        raise RuntimeError("source unavailable")

    monkeypatch.setattr(deps, "TencentQuoteAdapter", _boom)
    monkeypatch.setattr(deps, "AkshareQuoteAdapter", _boom)

    try:
        deps._build_quote_repo()
    except Exception as exc:
        from fastapi import HTTPException

        assert isinstance(exc, HTTPException)
        assert exc.status_code == 503
        assert exc.detail["code"] == "MARKET_DATA_SOURCE_UNAVAILABLE"
    else:
        raise AssertionError("expected HTTPException(503)")

def test_fallback_quote_repo_returns_empty_when_primary_empty_and_secondary_fails() -> None:
    class _Primary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            return []

    class _Secondary:
        def fetch(self, symbols, as_of, timeframe):
            del symbols, as_of, timeframe
            raise RuntimeError("secondary down")

    repo = deps._FallbackQuoteRepo(primary=_Primary(), secondary=_Secondary())
    out = repo.fetch(symbols=["600519.SH"], as_of="2026-04-01", timeframe="1m")
    assert out == []
