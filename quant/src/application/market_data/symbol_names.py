"""Load symbol -> Chinese short name from config/universes/symbol_names.json (mtime-cached)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")

# Bound walk-up depth (avoid infinite loops on odd FS layouts).
_QUANT_ROOT_WALK_MAX = 32


def _find_quant_package_root_walk_up(anchor: Path) -> Path | None:
    """Walk parents of ``anchor`` (file or directory) to find quant package root.

    Matches a directory ``Q`` where ``Q/config/universes`` exists, or a parent ``R``
    where ``R/quant/config/universes`` exists (monorepo layout; returns ``R/quant``).
    """
    cur = anchor.resolve()
    if cur.is_file():
        cur = cur.parent
    for _ in range(_QUANT_ROOT_WALK_MAX):
        if (cur / "config" / "universes").is_dir():
            return cur
        nested = cur / "quant"
        if (nested / "config" / "universes").is_dir():
            return nested.resolve()
        parent = cur.parent
        if parent == cur:
            break
        cur = parent
    return None


def resolve_quant_package_root() -> Path:
    """Directory containing quant's ``config/``, ``src/``, etc.

    Order:

    1. ``HIVEFLOW_QUANT_ROOT`` — absolute path to the ``quant`` package root.
    2. ``HIVEFLOW_ROOT`` or ``HIVEFLOW_REPO_ROOT`` — HiveFlow repo root (directory
       that contains ``quant/``), same as the Rust CLI.
    3. Walk upward from this module's path, then from ``os.getcwd()`` (aligns with
       Rust ``hiveflow_repo_root``; no env vars for typical repo checkouts).
    4. Fallback: ``Path(__file__).resolve().parents[3]`` (legacy layout).
    """
    env_q = os.environ.get("HIVEFLOW_QUANT_ROOT", "").strip()
    if env_q:
        return Path(env_q).expanduser().resolve()
    env_r = (
        os.environ.get("HIVEFLOW_ROOT", "").strip()
        or os.environ.get("HIVEFLOW_REPO_ROOT", "").strip()
    )
    if env_r:
        return (Path(env_r).expanduser().resolve() / "quant").resolve()
    discovered = _find_quant_package_root_walk_up(Path(__file__))
    if discovered is not None:
        return discovered
    try:
        discovered = _find_quant_package_root_walk_up(Path.cwd())
    except OSError:
        discovered = None
    if discovered is not None:
        return discovered
    return Path(__file__).resolve().parents[3]


def default_symbol_names_json_path() -> Path:
    """Path to quant/config/universes/symbol_names.json."""
    return resolve_quant_package_root() / "config" / "universes" / "symbol_names.json"


class FileSymbolNameLookup:
    """Reads symbol_names.json; reloads when file mtime changes."""

    def __init__(self, path: Path | None = None):
        self._path = path or default_symbol_names_json_path()
        self._mtime: float | None = None
        self._map: dict[str, str] = {}

    def reload_if_changed(self) -> None:
        path = self._path
        try:
            st = path.stat()
        except OSError:
            self._map = {}
            self._mtime = None
            return
        mtime = st.st_mtime
        if self._mtime == mtime:
            return
        self._mtime = mtime
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            self._map = {}
            return
        if not isinstance(raw, dict):
            self._map = {}
            return
        self._map = {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}

    def lookup(self, symbol: str) -> str:
        self.reload_if_changed()
        return self._map.get(symbol.strip(), "")

    def snapshot(self) -> dict[str, str]:
        """Current map after reload-if-changed (copy for read-only enrichment)."""
        self.reload_if_changed()
        return dict(self._map)

    def force_reload(self) -> None:
        self._mtime = None
        self.reload_if_changed()


def is_exchange_symbol(value: object) -> bool:
    return isinstance(value, str) and bool(_SYMBOL_PATTERN.fullmatch(value.strip()))


def enrich_json_with_symbol_names(obj: Any, names: dict[str, str]) -> None:
    """Recursively add symbol_name_zh next to stock symbol fields (in-place)."""
    if isinstance(obj, dict):
        sym = obj.get("symbol")
        if is_exchange_symbol(sym):
            name = names.get(str(sym).strip(), "")
            obj.setdefault("symbol_name_zh", name)
        for v in obj.values():
            enrich_json_with_symbol_names(v, names)
    elif isinstance(obj, list):
        for x in obj:
            enrich_json_with_symbol_names(x, names)
