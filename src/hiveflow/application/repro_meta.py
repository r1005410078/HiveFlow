"""可复现元数据工具。"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any

FEATURE_SET_VERSION = "signal-v1.0"
STYLE_PRESET_VERSION = "style-v1.0"


def stable_hash(payload: Any) -> str:
    """对任意可 JSON 序列化对象生成稳定哈希。"""
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def resolve_code_version() -> str:
    """解析当前代码版本（优先环境变量，其次 git）。"""
    override = os.environ.get("HIVEFLOW_CODE_VERSION")
    if override:
        return override

    root = Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(root),
            check=True,
            capture_output=True,
            text=True,
        )
        value = completed.stdout.strip()
        return value or "unknown"
    except Exception:
        return "unknown"
