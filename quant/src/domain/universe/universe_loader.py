from __future__ import annotations

import json
from pathlib import Path

# quant/src/domain/universe/ → parents[3] = quant/
_UNIVERSES_DIR = Path(__file__).resolve().parents[3] / "config" / "universes"


def load_universe(name: str) -> list[str]:
    """读取 quant/config/universes/<name>.txt，返回标的代码列表。

    跳过空行和 # 注释行。文件不存在时抛 FileNotFoundError。
    """
    path = _UNIVERSES_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Universe '{name}' not found at {path}")
    symbols = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            symbols.append(stripped)
    return symbols


def load_industry_map() -> dict[str, str]:
    """读取 quant/config/universes/industry_map.json，返回 {symbol: industry} dict。"""
    path = _UNIVERSES_DIR / "industry_map.json"
    return json.loads(path.read_text(encoding="utf-8"))
