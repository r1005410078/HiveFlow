from __future__ import annotations

import pytest

from domain.universe.universe_loader import load_industry_map, load_universe, load_universe_merged


def test_load_universe_returns_symbols():
    """load_universe("default") 返回 28 只标的，无空字符串，无注释行残留"""
    symbols = load_universe("default")
    assert len(symbols) == 28
    assert "300750.SZ" in symbols
    assert "601877.SH" in symbols
    assert all(s.strip() == s for s in symbols)
    assert all(len(s) > 0 for s in symbols)
    assert not any(s.startswith("#") for s in symbols)


def test_load_universe_skips_comments_and_blank(tmp_path, monkeypatch):
    """注释行和空行被跳过，只返回有效代码"""
    import domain.universe.universe_loader as loader

    monkeypatch.setattr(loader, "_UNIVERSES_DIR", tmp_path)
    (tmp_path / "test.txt").write_text(
        "# 注释行\n\n000001.SZ\n600519.SH\n# 另一注释\n\n",
        encoding="utf-8",
    )
    result = load_universe("test")
    assert result == ["000001.SZ", "600519.SH"]


def test_load_universe_raises_on_missing_file(tmp_path, monkeypatch):
    """不存在的 universe name 抛 FileNotFoundError"""
    import domain.universe.universe_loader as loader

    monkeypatch.setattr(loader, "_UNIVERSES_DIR", tmp_path)
    with pytest.raises(FileNotFoundError):
        load_universe("nonexistent")


def test_load_universe_merged_default_then_extra(tmp_path, monkeypatch):
    """先 base 再追加额外表；标的去重且 base 顺序优先。"""
    import domain.universe.universe_loader as loader

    monkeypatch.setattr(loader, "_UNIVERSES_DIR", tmp_path)
    (tmp_path / "default.txt").write_text("AAA.SH\nBBB.SH\n", encoding="utf-8")
    (tmp_path / "extra.txt").write_text("BBB.SH\nCCC.SH\n", encoding="utf-8")

    merged = load_universe_merged("default", ["extra"])
    assert merged == ["AAA.SH", "BBB.SH", "CCC.SH"]


def test_load_universe_merged_skips_duplicate_universe_names(tmp_path, monkeypatch):
    import domain.universe.universe_loader as loader

    monkeypatch.setattr(loader, "_UNIVERSES_DIR", tmp_path)
    (tmp_path / "default.txt").write_text("A\n", encoding="utf-8")
    (tmp_path / "u2.txt").write_text("B\n", encoding="utf-8")

    merged = load_universe_merged("default", ["default", "u2", "u2"])
    assert merged == ["A", "B"]


def test_load_industry_map_returns_dict():
    """load_industry_map() 返回 dict，default.txt 全部标的均有映射"""
    imap = load_industry_map()
    assert isinstance(imap, dict)
    symbols = load_universe("default")
    missing = [s for s in symbols if s not in imap]
    assert missing == [], f"symbols missing from industry_map.json: {missing}"
