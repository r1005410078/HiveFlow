"""Tests for symbol name lookup and JSON enrichment."""

from __future__ import annotations

import json
from pathlib import Path

from application.market_data.symbol_names import (
    FileSymbolNameLookup,
    _find_quant_package_root_walk_up,
    enrich_json_with_symbol_names,
    is_exchange_symbol,
    resolve_quant_package_root,
)


def test_is_exchange_symbol() -> None:
    assert is_exchange_symbol("600519.SH")
    assert is_exchange_symbol("000001.SZ")
    assert not is_exchange_symbol("600519")
    assert not is_exchange_symbol("foo")


def test_enrich_nested_and_setdefault() -> None:
    data = {
        "items": [
            {"symbol": "600519.SH", "close": 1.0},
            {"other": [{"symbol": "000001.SZ", "x": 1}]},
        ],
    }
    names = {"600519.SH": "贵州茅台", "000001.SZ": "平安银行"}
    enrich_json_with_symbol_names(data, names)
    assert data["items"][0]["symbol_name_zh"] == "贵州茅台"
    assert data["items"][1]["other"][0]["symbol_name_zh"] == "平安银行"
    # does not overwrite
    data["items"][0]["symbol_name_zh"] = "custom"
    enrich_json_with_symbol_names(data, names)
    assert data["items"][0]["symbol_name_zh"] == "custom"


def test_file_lookup_reload(tmp_path: Path) -> None:
    p = tmp_path / "symbol_names.json"
    p.write_text(json.dumps({"600519.SH": "茅台"}, ensure_ascii=False), encoding="utf-8")
    lu = FileSymbolNameLookup(path=p)
    assert lu.lookup("600519.SH") == "茅台"
    assert lu.lookup("000001.SZ") == ""
    p.write_text(json.dumps({"600519.SH": "贵州茅台", "000001.SZ": "平安"}, ensure_ascii=False), encoding="utf-8")
    lu.force_reload()
    assert lu.lookup("600519.SH") == "贵州茅台"
    assert lu.lookup("000001.SZ") == "平安"


def test_resolve_quant_package_root_env(monkeypatch, tmp_path: Path) -> None:
    q = tmp_path / "quant"
    q.mkdir()
    monkeypatch.delenv("HIVEFLOW_QUANT_ROOT", raising=False)
    monkeypatch.delenv("HIVEFLOW_ROOT", raising=False)
    monkeypatch.delenv("HIVEFLOW_REPO_ROOT", raising=False)
    monkeypatch.setenv("HIVEFLOW_QUANT_ROOT", str(q))
    assert resolve_quant_package_root() == q.resolve()

    monkeypatch.delenv("HIVEFLOW_QUANT_ROOT", raising=False)
    hive = tmp_path / "repo"
    hive.mkdir()
    (hive / "quant").mkdir()
    monkeypatch.setenv("HIVEFLOW_ROOT", str(hive))
    assert resolve_quant_package_root() == (hive / "quant").resolve()

    monkeypatch.delenv("HIVEFLOW_ROOT", raising=False)
    monkeypatch.setenv("HIVEFLOW_REPO_ROOT", str(hive))
    assert resolve_quant_package_root() == (hive / "quant").resolve()


def test_find_quant_package_root_walks_up_from_deep_file(tmp_path: Path) -> None:
    q = tmp_path / "HiveFlow" / "quant"
    (q / "config" / "universes").mkdir(parents=True)
    deep = q / "src" / "application" / "market_data" / "dummy.py"
    deep.parent.mkdir(parents=True)
    deep.write_text("#", encoding="utf-8")
    assert _find_quant_package_root_walk_up(deep) == q.resolve()


def test_find_quant_package_root_from_monorepo_parent(tmp_path: Path) -> None:
    repo = tmp_path / "mono"
    q = repo / "quant"
    (q / "config" / "universes").mkdir(parents=True)
    f = repo / "docs" / "nested" / "x.py"
    f.parent.mkdir(parents=True)
    f.write_text("", encoding="utf-8")
    assert _find_quant_package_root_walk_up(f) == q.resolve()


def test_find_quant_package_root_walk_up_accepts_directory_anchor(tmp_path: Path) -> None:
    q = tmp_path / "quant"
    (q / "config" / "universes").mkdir(parents=True)
    nested = q / "src" / "application"
    nested.mkdir(parents=True)
    assert _find_quant_package_root_walk_up(nested) == q.resolve()


def test_snapshot_after_reload(tmp_path: Path) -> None:
    p = tmp_path / "symbol_names.json"
    p.write_text("{}", encoding="utf-8")
    lu = FileSymbolNameLookup(path=p)
    m = lu.snapshot()
    assert m == {}
