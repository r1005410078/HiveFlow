# L0 标的池扩展 + 交易日历守卫 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 daily pipeline 标的池从 5 只扩至 28 只（6 行业），消除三处重复的行业映射硬编码，并在非交易日自动跳过计算。

**Architecture:** 新建 `domain/universe/universe_loader.py` 提供 `load_universe()` 和 `load_industry_map()` 两个纯函数，读取 `quant/config/universes/` 下的配置文件。三个服务文件（optimizer / risk_gate / signal_engineering）删除各自硬编码的 `_INDUSTRY_MAP`，改为模块级调用 `load_industry_map()`。`daily_run_service.py` 改用 `load_universe("default")` 并在入口加交易日历守卫。

**Tech Stack:** Python 3.13, pathlib, json（标准库），exchange_calendars（已有）

---

## File Map

| 操作 | 文件 |
|------|------|
| 新建 | `quant/config/universes/default.txt` |
| 新建 | `quant/config/universes/industry_map.json` |
| 新建 | `quant/src/domain/universe/__init__.py` |
| 新建 | `quant/src/domain/universe/universe_loader.py` |
| 新建 | `quant/tests/unit/universe/__init__.py` |
| 新建 | `quant/tests/unit/universe/test_universe_loader.py` |
| 修改 | `quant/src/application/portfolio/optimizer_service.py` |
| 修改 | `quant/src/application/risk/risk_gate_service.py` |
| 修改 | `quant/src/application/signal/signal_engineering_service.py` |
| 修改 | `quant/src/application/daily_run_service.py` |
| 修改 | `quant/tests/contract/test_http_daily_endpoint.py` |

---

### Task 1: 创建配置文件（default.txt + industry_map.json）

**Files:**
- Create: `quant/config/universes/default.txt`
- Create: `quant/config/universes/industry_map.json`

配置文件无业务逻辑，不需要 TDD，直接创建后提交。

- [ ] **Step 1: 创建 `default.txt`**

内容如下（28 只标的，6 行业）：

```
# HiveFlow 精选标的池（L0 默认运行池）
# 覆盖 6 个行业：new_energy / robotics / semiconductor / pcb / power / power_grid
# 每行业 4-6 只，保证行业中性化 OLS 有实质意义
300750.SZ
002594.SZ
601012.SH
688599.SH
300024.SZ
300124.SZ
002747.SZ
688015.SH
603486.SH
002230.SZ
688041.SH
603501.SH
002049.SZ
688012.SH
603986.SH
688716.SH
002463.SZ
002916.SZ
600183.SH
002384.SZ
600900.SH
601985.SH
600025.SH
600905.SH
601669.SH
600875.SH
601727.SH
601877.SH
```

- [ ] **Step 2: 创建 `industry_map.json`**

内容如下（28 只新标的 + 原有 4 只未收录的标的，共 32 条）：

```json
{
  "300750.SZ": "new_energy",
  "002594.SZ": "new_energy",
  "601012.SH": "new_energy",
  "688599.SH": "new_energy",
  "300024.SZ": "robotics",
  "300124.SZ": "robotics",
  "002747.SZ": "robotics",
  "688015.SH": "robotics",
  "603486.SH": "robotics",
  "002230.SZ": "robotics",
  "688041.SH": "semiconductor",
  "603501.SH": "semiconductor",
  "002049.SZ": "semiconductor",
  "688012.SH": "semiconductor",
  "603986.SH": "semiconductor",
  "688716.SH": "semiconductor",
  "002463.SZ": "pcb",
  "002916.SZ": "pcb",
  "600183.SH": "pcb",
  "002384.SZ": "pcb",
  "600900.SH": "power",
  "601985.SH": "power",
  "600025.SH": "power",
  "600905.SH": "power",
  "601669.SH": "power_grid",
  "600875.SH": "power_grid",
  "601727.SH": "power_grid",
  "601877.SH": "power_grid",
  "000001.SZ": "banking",
  "600519.SH": "food_beverage",
  "601318.SH": "insurance",
  "000333.SZ": "appliance"
}
```

后 4 条（banking/food_beverage/insurance/appliance）保留原有 5 只中未收录到 default.txt 的标的，确保现有单元测试中使用旧标的的 case 不会因找不到行业映射而行为改变（未找到时 fallback 为 `"other"`，行为不变，但显式收录更清晰）。

- [ ] **Step 3: 提交配置文件**

```bash
cd /Users/rongts/HiveFlow
git add quant/config/universes/default.txt quant/config/universes/industry_map.json
git commit -m "feat(l0): add default universe (28 symbols, 6 industries) and industry_map.json"
```

---

### Task 2: `universe_loader.py` + 单元测试（TDD）

**Files:**
- Create: `quant/src/domain/universe/__init__.py`
- Create: `quant/src/domain/universe/universe_loader.py`
- Create: `quant/tests/unit/universe/__init__.py`
- Create: `quant/tests/unit/universe/test_universe_loader.py`

- [ ] **Step 1: 创建空 `__init__.py` 文件**

```bash
touch quant/src/domain/universe/__init__.py
touch quant/tests/unit/universe/__init__.py
```

- [ ] **Step 2: 写测试文件（先写测试，此时实现不存在）**

创建 `quant/tests/unit/universe/test_universe_loader.py`：

```python
from __future__ import annotations

import json

import pytest

from domain.universe.universe_loader import load_industry_map, load_universe


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


def test_load_industry_map_returns_dict():
    """load_industry_map() 返回 dict，default.txt 全部标的均有映射"""
    imap = load_industry_map()
    assert isinstance(imap, dict)
    symbols = load_universe("default")
    missing = [s for s in symbols if s not in imap]
    assert missing == [], f"symbols missing from industry_map.json: {missing}"
```

- [ ] **Step 3: 运行测试，确认失败（模块不存在）**

```bash
cd quant && uv run python -m pytest tests/unit/universe/test_universe_loader.py -v 2>&1 | head -20
```

预期输出：`ModuleNotFoundError: No module named 'domain.universe'`

- [ ] **Step 4: 实现 `universe_loader.py`**

创建 `quant/src/domain/universe/universe_loader.py`：

```python
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
```

- [ ] **Step 5: 运行测试，确认全部通过**

```bash
cd quant && uv run python -m pytest tests/unit/universe/test_universe_loader.py -v
```

预期输出：`4 passed`

- [ ] **Step 6: 运行架构测试，确认不需要修改**

```bash
cd quant && uv run pytest tests/architecture -v
```

预期输出：所有架构测试通过（`domain.universe` 属于 domain 层，application 层 import domain 是允许的，现有架构测试不拦截此路径）。

- [ ] **Step 7: 提交**

```bash
cd /Users/rongts/HiveFlow
git add quant/src/domain/universe/ quant/tests/unit/universe/
git commit -m "feat(l0): add universe_loader with load_universe() and load_industry_map()"
```

---

### Task 3: 消除三处重复的 `_INDUSTRY_MAP` 硬编码

**Files:**
- Modify: `quant/src/application/portfolio/optimizer_service.py`
- Modify: `quant/src/application/risk/risk_gate_service.py`
- Modify: `quant/src/application/signal/signal_engineering_service.py`

纯重构，行为不变。改完后运行全量测试验证无回归。

- [ ] **Step 1: 修改 `optimizer_service.py`**

将文件开头的：

```python
_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}
```

替换为：

```python
from domain.universe.universe_loader import load_industry_map

_INDUSTRY_MAP: dict[str, str] = load_industry_map()
```

`import` 放在文件顶部现有 import 块的末尾（在 `_logger = ...` 行之前）。

- [ ] **Step 2: 修改 `risk_gate_service.py`**

将文件开头的：

```python
_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}
```

替换为：

```python
from domain.universe.universe_loader import load_industry_map

_INDUSTRY_MAP: dict[str, str] = load_industry_map()
```

- [ ] **Step 3: 修改 `signal_engineering_service.py`**

将文件开头的：

```python
_INDUSTRY_MAP: dict[str, str] = {
    "000001.SZ": "banking",
    "600519.SH": "food_beverage",
    "300750.SZ": "new_energy",
    "601318.SH": "insurance",
    "000333.SZ": "appliance",
}
```

替换为：

```python
from domain.universe.universe_loader import load_industry_map

_INDUSTRY_MAP: dict[str, str] = load_industry_map()
```

- [ ] **Step 4: 运行全量测试，验证无回归**

```bash
cd quant && uv run python -m pytest -q
```

预期输出：所有测试通过，无新增失败。

- [ ] **Step 5: 运行 lint 检查**

```bash
cd quant && uv run ruff check .
```

预期输出：`All checks passed!`

- [ ] **Step 6: 提交**

```bash
cd /Users/rongts/HiveFlow
git add quant/src/application/portfolio/optimizer_service.py \
        quant/src/application/risk/risk_gate_service.py \
        quant/src/application/signal/signal_engineering_service.py
git commit -m "refactor(l0): replace hardcoded _INDUSTRY_MAP with load_industry_map() in 3 services"
```

---

### Task 4: `daily_run_service.py` — 扩标的池 + 交易日历守卫 + 测试

**Files:**
- Modify: `quant/src/application/daily_run_service.py`
- Modify: `quant/tests/contract/test_http_daily_endpoint.py`

- [ ] **Step 1: 先写非交易日测试（TDD）**

在 `quant/tests/contract/test_http_daily_endpoint.py` 末尾追加：

```python
def test_daily_skips_non_trading_day():
    """非交易日（周日）返回 skipped=true，不触发任何计算"""
    from unittest.mock import patch

    app = create_app()
    client = TestClient(app)

    with patch("application.daily_run_service.is_sse_trading_day", return_value=False):
        resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-05"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline daily"
    assert payload["data"]["as_of"] == "2026-04-05"
    assert payload["data"]["skipped"] is True
    assert payload["data"]["skip_reason"] == "non_trading_day"
    assert "factor_snapshot" not in payload["data"]
```

- [ ] **Step 2: 运行测试，确认新 case 失败**

```bash
cd quant && uv run python -m pytest tests/contract/test_http_daily_endpoint.py::test_daily_skips_non_trading_day -v
```

预期输出：`FAILED` — `is_sse_trading_day` 还未在 `daily_run_service` 中 import，patch 不生效或守卫不存在。

- [ ] **Step 3: 修改 `daily_run_service.py`**

在文件顶部 import 块末尾添加：

```python
from domain.market_data.sse_calendar import is_sse_trading_day
from domain.universe.universe_loader import load_universe
```

将 `run_daily()` 函数开头的硬编码 symbols 列表：

```python
    symbols = [
        "000001.SZ",
        "600519.SH",
        "300750.SZ",
        "601318.SH",
        "000333.SZ",
    ]
```

替换为：

```python
    symbols = load_universe("default")
```

在 `run_id = ...` 行之后、`symbols = ...` 行之前，插入交易日历守卫：

```python
    if not is_sse_trading_day(as_of):
        return ok_output(
            command="hf pipeline daily",
            run_id=run_id,
            data={"as_of": as_of, "skipped": True, "skip_reason": "non_trading_day"},
        )
```

修改后 `run_daily()` 开头结构如下：

```python
def run_daily(
    as_of: str,
    root,
    bar_store=None,
    score_version: str = "l2-score-v1.1",
    top_n: int = 5,
) -> dict:
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    if not is_sse_trading_day(as_of):
        return ok_output(
            command="hf pipeline daily",
            run_id=run_id,
            data={"as_of": as_of, "skipped": True, "skip_reason": "non_trading_day"},
        )

    symbols = load_universe("default")
    # 以下原有逻辑不变...
```

- [ ] **Step 4: 运行新测试，确认通过**

```bash
cd quant && uv run python -m pytest tests/contract/test_http_daily_endpoint.py::test_daily_skips_non_trading_day -v
```

预期输出：`PASSED`

- [ ] **Step 5: 运行全量测试，验证无回归**

```bash
cd quant && uv run python -m pytest -q
```

预期输出：所有测试通过。若现有 `test_post_daily_contract` 因标的池从 5 只变 28 只而超时或行为变化，检查：该测试使用 `bar_store=None`（deterministic 快照模式），28 只标的下仍可正常运行，无副作用。

- [ ] **Step 6: 运行 lint**

```bash
cd quant && uv run ruff check .
```

预期输出：`All checks passed!`

- [ ] **Step 7: 运行全量 CI 门禁**

```bash
cd /Users/rongts/HiveFlow && make check
```

预期输出：Python tests + lint + architecture-check + validate-cli-output + rust-test 全部通过。

- [ ] **Step 8: 提交**

```bash
cd /Users/rongts/HiveFlow
git add quant/src/application/daily_run_service.py \
        quant/tests/contract/test_http_daily_endpoint.py
git commit -m "feat(l0): expand default universe to 28 symbols; add non-trading-day guard to daily pipeline"
```
