from __future__ import annotations

import os
from urllib.parse import quote_plus

# #region agent log
_DBG_CONNECT_SEQ = 0


def _agent_debug_ndjson(message: str, data: dict, hypothesis_id: str, location: str) -> None:
    import json
    import time

    try:
        payload = {
            "sessionId": "e56e61",
            "timestamp": int(time.time() * 1000),
            "location": location,
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
        }
        with open(
            "/Users/rongts/strat-flow/.cursor/debug-e56e61.log",
            "a",
            encoding="utf-8",
        ) as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


# #endregion


def has_db_config() -> bool:
    return bool(os.getenv("HF_DB_DSN") or os.getenv("HF_DB_HOST") or os.getenv("POSTGRES_HOST"))


def _build_dsn_from_env() -> str:
    user = os.getenv("HF_DB_USER") or os.getenv("POSTGRES_USER") or "hiveflow"
    password = os.getenv("HF_DB_PASSWORD") or os.getenv("POSTGRES_PASSWORD") or "hiveflow_local_dev"
    host = os.getenv("HF_DB_HOST") or os.getenv("POSTGRES_HOST") or "127.0.0.1"
    port = os.getenv("HF_DB_PORT") or os.getenv("POSTGRES_PORT") or "5432"
    dbname = os.getenv("HF_DB_NAME") or os.getenv("POSTGRES_DB") or "hiveflow"
    return f"postgresql://{quote_plus(user)}:{quote_plus(password)}@{host}:{port}/{dbname}"


def open_db_connection_from_env():
    dsn = os.getenv("HF_DB_DSN") or _build_dsn_from_env()
    timeout = int(os.getenv("HF_DB_CONNECT_TIMEOUT", "5"))

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "psycopg is required for database mode. Install quant dependencies first."
        ) from exc

    global _DBG_CONNECT_SEQ
    try:
        conn = psycopg.connect(dsn, connect_timeout=timeout, autocommit=False)
    except Exception as exc:
        # #region agent log
        _agent_debug_ndjson(
            "db_connect_failed",
            {"err_type": type(exc).__name__, "err_msg": str(exc)[:200]},
            "H1",
            "db_connection.py:open_db_connection_from_env",
        )
        # #endregion
        raise
    # #region agent log
    _DBG_CONNECT_SEQ += 1
    _agent_debug_ndjson(
        "db_connect_open",
        {"open_seq": _DBG_CONNECT_SEQ, "conn_id": id(conn)},
        "H1",
        "db_connection.py:open_db_connection_from_env",
    )
    # #endregion
    return conn
