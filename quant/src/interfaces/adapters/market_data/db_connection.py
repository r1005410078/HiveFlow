from __future__ import annotations

import os
from urllib.parse import quote_plus


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

    return psycopg.connect(dsn, connect_timeout=timeout, autocommit=False)
