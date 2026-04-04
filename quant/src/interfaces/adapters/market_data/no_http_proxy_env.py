"""Make ``requests`` (akshare) reach market-data hosts without a broken system proxy."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

# Hosts used by akshare / eastmoney; NO_PROXY lets urllib3 skip HTTP(S)_PROXY when we cannot pop env
# (e.g. proxy injected after startup) or as extra belt-and-suspenders after popping proxy vars.
_NO_PROXY_EXTRA = (
    "eastmoney.com",
    ".eastmoney.com",
    "push2.eastmoney.com",
    "localhost",
    "127.0.0.1",
)


def _merged_no_proxy() -> str:
    parts: list[str] = []
    for key in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(key)
        if raw:
            parts.extend(p.strip() for p in raw.split(",") if p.strip())
    for h in _NO_PROXY_EXTRA:
        if h not in parts:
            parts.append(h)
    return ",".join(dict.fromkeys(parts))


@contextmanager
def disabled_http_proxy_env() -> Iterator[None]:
    """Bypass misconfigured HTTP proxies for public market-data APIs.

    1. Temporarily unset HTTP(S)_PROXY / ALL_PROXY (and lowercase variants).
    2. Extend NO_PROXY / no_proxy with eastmoney-related hosts so urllib3 skips proxies
       if any proxy setting is re-applied mid-process.

    Restores previous environment after the block.
    """
    saved_proxy: dict[str, str] = {}
    saved_no_proxy: dict[str, str | None] = {}
    try:
        for key in _PROXY_ENV_KEYS:
            if key in os.environ:
                saved_proxy[key] = os.environ.pop(key)
        for key in ("NO_PROXY", "no_proxy"):
            saved_no_proxy[key] = os.environ.get(key)
        merged = _merged_no_proxy()
        os.environ["NO_PROXY"] = merged
        os.environ["no_proxy"] = merged
        yield
    finally:
        for key, value in saved_no_proxy.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key, value in saved_proxy.items():
            os.environ[key] = value
