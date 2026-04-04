"""Middleware: add symbol_name_zh to JSON bodies where symbol is a HiveFlow exchange code."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from application.market_data.symbol_names import (
    FileSymbolNameLookup,
    enrich_json_with_symbol_names,
)

_lookup = FileSymbolNameLookup()


def get_symbol_name_lookup() -> FileSymbolNameLookup:
    return _lookup


class SymbolNameJsonMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if response.status_code not in (200, 201, 202):
            return response
        ct = (response.headers.get("content-type") or "").lower()
        if "application/json" not in ct:
            return response
        body: bytes | None = None
        if hasattr(response, "body"):
            try:
                body = response.body
            except (AttributeError, AssertionError, RuntimeError):
                body = None
        if body is None and hasattr(response, "body_iterator"):
            chunks: list[bytes] = []
            async for part in response.body_iterator:
                chunks.append(part)
            body = b"".join(chunks)
        if not body:
            return response
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return response
        names = _lookup.snapshot()
        enrich_json_with_symbol_names(data, names)
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in ("content-length", "content-type")
        }
        bg = getattr(response, "background", None)
        return JSONResponse(
            content=data,
            status_code=response.status_code,
            headers=headers,
            background=bg,
        )
