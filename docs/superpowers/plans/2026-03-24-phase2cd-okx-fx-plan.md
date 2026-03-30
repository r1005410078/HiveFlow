# Phase 2-C/D OKX 接口化 + 跨市场货币折算 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 OKX 实现 `PositionProvider` 抽象接口，引入 `FxRateProvider` 支持 CNY/USDT 双货币折算，升级 `positions list` 并新增 `portfolio summary` 命令展示跨市场统一视图。

**Architecture:** 在现有 Clean Architecture 四层结构上做加法：Domain 层 `Position` 加 `currency` 字段 + 轻量迁移；新增 `FxRateProvider`（akshare 主 + config 回退）；`OkxProvider` 实现 `PositionProvider` 接口；新增 `build_portfolio_summary` 应用层函数；CLI 升级 `positions list` 并新增 `portfolio summary` 命令。

**Tech Stack:** Python, SQLModel, SQLite, akshare（已有依赖）, Typer, Rich

---

## 文件结构

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `src/hiveflow/domain/positions.py` | 修改 | 加 `currency: str = "USDT"` 字段 |
| `src/hiveflow/config.py` | 修改 | 加 `cny_usdt_rate: float = 7.25` 配置项 |
| `src/hiveflow/db.py` | 修改 | 加 `currency` 列轻量迁移 |
| `src/hiveflow/infrastructure/fx_rate_provider.py` | 新建 | FxRateProvider，akshare 主 + config 回退 |
| `src/hiveflow/infrastructure/okx/okx_provider.py` | 修改 | 继承 PositionProvider，fetch_positions 返回 list[Position] |
| `src/hiveflow/application/portfolio.py` | 新建 | PositionWithFx, PortfolioSummary, build_portfolio_summary |
| `src/hiveflow/cli.py` | 修改 | positions list 加折算列；新增 portfolio_app + summary 命令 |
| `tests/test_phase2cd.py` | 新建 | 所有新功能的测试 |

---

## Chunk 1: Domain + Migration

### Task 1: Position.currency 字段 + 轻量迁移

**Files:**
- Modify: `src/hiveflow/domain/positions.py`
- Modify: `src/hiveflow/config.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_phase2cd.py`

**背景：** `Position` 是 SQLModel 实体（`src/hiveflow/domain/positions.py`），目前字段为 `id, symbol, quantity, market_value, weight, updated_at, market`。需要加 `currency: str = "USDT"` 并在 `db.py` 的 `_run_lightweight_migrations` 中追加 ALTER TABLE。

- [ ] **Step 1: 写失败测试**

新建 `tests/test_phase2cd.py`：

```python
# tests/test_phase2cd.py
"""Phase 2-C/D 测试：OKX 接口化 + 跨市场货币折算。"""
from __future__ import annotations

import os
import json
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position


def test_position_has_currency_field() -> None:
    """Position 实体应有 currency 字段，默认值 'USDT'。"""
    p = Position(symbol="BTC", quantity=0.1, market_value=1000.0, weight=0.5)
    assert p.currency == "USDT"


def test_position_currency_can_be_cny() -> None:
    """Position currency 可以设置为 'CNY'。"""
    p = Position(symbol="000001.SZ", quantity=100.0, market_value=1000.0,
                 weight=0.1, market="cn_a_share", currency="CNY")
    assert p.currency == "CNY"


def test_migration_adds_currency_column_with_default(tmp_path) -> None:
    """旧数据库（无 currency 列）迁移后，已有行的 currency == 'USDT'。"""
    import sqlite3
    db_path = tmp_path / "old.db"
    # 模拟旧数据库：手动建表（不含 currency 列）
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE position (id INTEGER PRIMARY KEY, symbol TEXT, "
        "quantity REAL DEFAULT 0, market_value REAL DEFAULT 0, "
        "weight REAL DEFAULT 0, updated_at TEXT, market TEXT DEFAULT 'crypto')"
    )
    conn.execute("INSERT INTO position (symbol, quantity, market_value, weight) "
                 "VALUES ('BTC', 0.1, 1000.0, 0.5)")
    conn.commit()
    conn.close()

    # 运行迁移
    settings = Settings(database_url=f"sqlite:///{db_path}")
    create_all_tables(settings)

    # 验证迁移后旧行有默认 currency
    conn2 = sqlite3.connect(str(db_path))
    row = conn2.execute("SELECT currency FROM position WHERE symbol='BTC'").fetchone()
    conn2.close()
    assert row is not None
    assert row[0] == "USDT"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/rongts/strat-flow
uv run python -m pytest tests/test_phase2cd.py::test_position_has_currency_field -v
```

Expected: FAIL — `Position` 没有 `currency` 属性。

- [ ] **Step 3: 给 Position 加 currency 字段**

编辑 `src/hiveflow/domain/positions.py`，在 `market: str = "crypto"` 后加一行：

```python
currency: str = "USDT"   # "USDT" | "CNY"，默认向后兼容
```

- [ ] **Step 4: 在 db.py 加迁移代码**

打开 `src/hiveflow/db.py`，在 `_run_lightweight_migrations` 函数内，找到最后一个 `if "xxx" in tables:` 块的结尾，**追加**以下代码块（注意缩进，与上方同级）：

```python
        # position 表：currency 列（Phase 2-C/D）
        if "position" in tables:
            pos_col_names = {row[1] for row in conn.exec_driver_sql(
                "PRAGMA table_info(position)"
            ).fetchall()}
            if "currency" not in pos_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE position ADD COLUMN currency VARCHAR DEFAULT 'USDT'"
                )
```

- [ ] **Step 5: 运行全部新测试**

```bash
uv run python -m pytest tests/test_phase2cd.py -v
```

Expected: 3 passed。

- [ ] **Step 6: 全量回归**

```bash
uv run python -m pytest -q
```

Expected: 430+ passed，0 failed。

- [ ] **Step 7: 给 Settings 加 cny_usdt_rate**

编辑 `src/hiveflow/config.py`，在 `tushare_token` 字段后加：

```python
    # 货币折算回退汇率（env: HIVEFLOW_CNY_USDT_RATE，FxRateProvider akshare 失败时使用）
    cny_usdt_rate: float = 7.25
```

- [ ] **Step 8: Commit**

```bash
git add src/hiveflow/domain/positions.py src/hiveflow/config.py src/hiveflow/db.py tests/test_phase2cd.py
git commit -m "feat: Position 加 currency 字段 + 轻量迁移 + Settings.cny_usdt_rate"
```

---

## Chunk 2: FxRateProvider

### Task 2: FxRateProvider（akshare 主 + config 回退）

**Files:**
- Create: `src/hiveflow/infrastructure/fx_rate_provider.py`
- Test: `tests/test_phase2cd.py`（追加）

**背景：** 需要一个独立的汇率提供者，用 akshare 拉取中国银行美元折算价（即 CNY/USD），将其作为 CNY/USDT 近似汇率。akshare 失败时用 `Settings.cny_usdt_rate` 回退，永远不抛异常。akshare 已在项目中按模块级变量方式导入（`import akshare as _ak_mod`），以便在测试中 patch。

- [ ] **Step 1: 写失败测试（追加到 test_phase2cd.py）**

```python
# ---- FxRateProvider ----

import hiveflow.infrastructure.fx_rate_provider as _fx_mod  # noqa: E402


def test_fx_rate_provider_akshare_success() -> None:
    """akshare 正常返回时，get_cny_per_usdt 返回 (rate, 'akshare')。"""
    import pandas as pd
    mock_df = pd.DataFrame({"中行折算价": ["7.28", "7.30"]})
    mock_ak = MagicMock()
    mock_ak.currency_boc_sina.return_value = mock_df
    original = _fx_mod.akshare
    _fx_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.fx_rate_provider import FxRateProvider
        provider = FxRateProvider(Settings(cny_usdt_rate=7.25))
        rate, source = provider.get_cny_per_usdt()
    finally:
        _fx_mod.akshare = original
    assert rate == 7.30
    assert source == "akshare"


def test_fx_rate_provider_akshare_failure_fallback() -> None:
    """akshare 失败时返回 config 回退值，不抛异常，发出 warning。"""
    mock_ak = MagicMock()
    mock_ak.currency_boc_sina.side_effect = Exception("network error")
    original = _fx_mod.akshare
    _fx_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.fx_rate_provider import FxRateProvider
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            provider = FxRateProvider(Settings(cny_usdt_rate=7.25))
            rate, source = provider.get_cny_per_usdt()
    finally:
        _fx_mod.akshare = original
    assert rate == 7.25
    assert source == "config_fallback"
    assert len(w) >= 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_phase2cd.py::test_fx_rate_provider_akshare_success -v
```

Expected: FAIL — `FxRateProvider` 不存在。

- [ ] **Step 3: 实现 FxRateProvider**

新建 `src/hiveflow/infrastructure/fx_rate_provider.py`：

```python
# src/hiveflow/infrastructure/fx_rate_provider.py
"""汇率提供者：akshare 主 + Settings 回退，永远不抛异常。"""
from __future__ import annotations

import warnings

from hiveflow.config import Settings

try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]


class FxRateProvider:
    """获取 CNY/USDT 汇率。

    优先使用 akshare（中国银行美元折算中间价），失败时使用 Settings.cny_usdt_rate 回退。
    get_cny_per_usdt() 永远不抛异常，始终返回有效汇率。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def get_cny_per_usdt(self) -> tuple[float, str]:
        """返回 (汇率, 来源)。汇率含义：1 USDT ≈ ? CNY。

        来源：
        - "akshare"：akshare.currency_boc_sina 实时数据
        - "config_fallback"：Settings.cny_usdt_rate（默认 7.25）
        """
        import hiveflow.infrastructure.fx_rate_provider as _self_mod
        _ak = _self_mod.akshare
        if _ak is not None:
            try:
                df = _ak.currency_boc_sina(symbol="美元")
                if df is not None and not df.empty and "中行折算价" in df.columns:
                    rate = float(df.iloc[-1]["中行折算价"])
                    return rate, "akshare"
            except Exception as e:
                warnings.warn(f"FxRateProvider akshare 获取汇率失败: {e}，使用配置回退值")
        return self._settings.cny_usdt_rate, "config_fallback"
```

- [ ] **Step 4: 运行新测试**

```bash
uv run python -m pytest tests/test_phase2cd.py::test_fx_rate_provider_akshare_success tests/test_phase2cd.py::test_fx_rate_provider_akshare_failure_fallback -v
```

Expected: 2 passed。

- [ ] **Step 5: 全量回归**

```bash
uv run python -m pytest -q
```

Expected: 432+ passed，0 failed。

- [ ] **Step 6: Commit**

```bash
git add src/hiveflow/infrastructure/fx_rate_provider.py tests/test_phase2cd.py
git commit -m "feat: 新增 FxRateProvider（akshare 主 + config 回退）"
```

---

## Chunk 3: OkxProvider 接口化

### Task 3: OkxProvider 实现 PositionProvider，fetch_positions 返回 list[Position]

**Files:**
- Modify: `src/hiveflow/infrastructure/okx/okx_provider.py`
- Modify: `src/hiveflow/application/sync.py`（适配新返回类型）
- Test: `tests/test_phase2cd.py`（追加）

**背景：**
- 当前 `OkxProvider.fetch_positions()` 返回 `list[OkxPosition]`（内部 dataclass）
- `sync_from_okx` 用 `p.market_value_usdt` 字段（`OkxPosition` 专有）
- 改造后：`fetch_positions()` 返回 `list[Position]`（domain 实体），`currency="USDT"`，`market="crypto"`
- `sync_from_okx` 改用 `p.market_value`（`Position` 的通用字段）
- 原有 `OkxPosition` dataclass 保留为内部中间结构，不对外暴露

- [ ] **Step 1: 写失败测试（追加到 test_phase2cd.py）**

```python
# ---- OkxProvider 接口化 ----

from hiveflow.domain.providers import PositionProvider


def _make_okx_provider_with_mock_http(positions_data: list[dict]) -> "OkxProvider":
    """创建一个 mock 掉 HTTP 层的 OkxProvider。"""
    from hiveflow.infrastructure.okx.okx_provider import OkxProvider
    provider = OkxProvider.__new__(OkxProvider)
    provider._get_auth = MagicMock(return_value=positions_data)
    return provider


def test_okx_provider_implements_position_provider() -> None:
    """OkxProvider 是 PositionProvider 的子类。"""
    from hiveflow.infrastructure.okx.okx_provider import OkxProvider
    provider = OkxProvider.__new__(OkxProvider)
    assert isinstance(provider, PositionProvider)


def test_okx_provider_fetch_positions_returns_domain_positions() -> None:
    """fetch_positions() 返回 list[Position]，每项 currency='USDT'，market='crypto'。"""
    mock_data = [{
        "details": [
            {"ccy": "BTC", "availBal": "0.12", "eqUsd": "8400.0"},
            {"ccy": "ETH", "availBal": "2.5", "eqUsd": "6200.0"},
        ]
    }]
    provider = _make_okx_provider_with_mock_http(mock_data)
    positions = provider.fetch_positions()

    assert len(positions) == 2
    for p in positions:
        assert isinstance(p, Position)
        assert p.currency == "USDT"
        assert p.market == "crypto"

    btc = next(p for p in positions if p.symbol == "BTC")
    assert btc.quantity == 0.12
    assert btc.market_value == 8400.0


def test_okx_provider_fetch_positions_filters_zero_balance() -> None:
    """fetch_positions() 过滤掉 availBal <= 0 的资产。"""
    mock_data = [{
        "details": [
            {"ccy": "BTC", "availBal": "0.0", "eqUsd": "0.0"},
            {"ccy": "ETH", "availBal": "2.5", "eqUsd": "6200.0"},
        ]
    }]
    provider = _make_okx_provider_with_mock_http(mock_data)
    positions = provider.fetch_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "ETH"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_phase2cd.py::test_okx_provider_implements_position_provider -v
```

Expected: FAIL — `OkxProvider` 没有继承 `PositionProvider`。

- [ ] **Step 3: 更新 PositionProvider 接口签名（可选但推荐）**

打开 `src/hiveflow/domain/providers.py`，将 `fetch_positions` 返回类型从 `list` 改为 `list[Position]`：

```python
from hiveflow.domain.positions import Position  # 文件顶部加此导入（如未有）

class PositionProvider(ABC):
    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        """返回当前账户持仓列表。"""
        ...
```

- [ ] **Step 4: 修改 OkxProvider**

打开 `src/hiveflow/infrastructure/okx/okx_provider.py`：

1. 在文件顶部导入处加：
```python
from hiveflow.domain.positions import Position
from hiveflow.domain.providers import PositionProvider
```

2. 修改类定义，继承 `PositionProvider`：
```python
class OkxProvider(PositionProvider):
```

3. 将 `fetch_positions` 方法改为返回 `list[Position]`：
```python
def fetch_positions(self) -> list[Position]:
    """拉取现货余额（GET /api/v5/account/balance），返回 list[Position]。"""
    data = self._get_auth("/api/v5/account/balance")
    result = []
    details = data[0].get("details", []) if data else []
    for item in details:
        symbol = item.get("ccy", "").upper()
        if not symbol:
            continue
        qty = float(item.get("availBal") or 0)
        val = float(item.get("eqUsd") or 0)
        if qty <= 0:
            continue
        result.append(Position(
            symbol=symbol,
            quantity=qty,
            market_value=val,
            weight=0.0,        # weight 在 sync_from_okx 中计算，这里先填 0
            market="crypto",
            currency="USDT",
        ))
    return result
```

注意：`OkxPosition` dataclass 保留不动，其他方法（`fetch_tickers` 等）不变。

- [ ] **Step 5: 修改 sync_from_okx 适配新返回类型**

打开 `src/hiveflow/application/sync.py`，找到 `sync_from_okx` 函数。

原来用 `p.market_value_usdt`（`OkxPosition` 专有字段），改为 `p.market_value`（`Position` 通用字段）：

找到：
```python
    total_value = sum(p.market_value_usdt for p in okx_positions)
```
改为：
```python
    total_value = sum(p.market_value for p in okx_positions)
```

找到（写入数据库部分）：
```python
            session.add(Position(
                symbol=p.symbol, quantity=p.quantity,
                market_value=p.market_value_usdt, weight=weight,
            ))
```
改为：
```python
            session.add(Position(
                symbol=p.symbol, quantity=p.quantity,
                market_value=p.market_value, weight=weight,
                market=p.market, currency=p.currency,
            ))
```

找到 USDT 过滤的 ticker fetch（`inst_ids` 构建那一行）：
```python
    inst_ids = [f"{p.symbol}-USDT" for p in okx_positions if p.symbol != "USDT"]
```
这行不需要改（逻辑相同）。

- [ ] **Step 6: 运行新测试**

```bash
uv run python -m pytest tests/test_phase2cd.py -k "okx" -v
```

Expected: 3 passed。

- [ ] **Step 7: 全量回归（重要！sync 改了要确保没破坏）**

```bash
uv run python -m pytest -q
```

Expected: 435+ passed，0 failed。

- [ ] **Step 8: Commit**

```bash
git add src/hiveflow/domain/providers.py src/hiveflow/infrastructure/okx/okx_provider.py src/hiveflow/application/sync.py tests/test_phase2cd.py
git commit -m "feat: OkxProvider 实现 PositionProvider 接口，fetch_positions 返回 list[Position]"
```

---

## Chunk 4: Application + CLI

### Task 4: build_portfolio_summary 应用层

**Files:**
- Create: `src/hiveflow/application/portfolio.py`
- Test: `tests/test_phase2cd.py`（追加）

**背景：**
- `build_portfolio_summary` 从数据库读所有 `Position`
- 调用 `FxRateProvider.get_cny_per_usdt()` 获取汇率
- 按 `currency` 折算：USDT 持仓乘汇率得 CNY，CNY 持仓除汇率得 USDT
- `breakdown` 按 market 分组，每组用本位货币展示金额
- 空持仓时返回合法的零值 PortfolioSummary

- [ ] **Step 1: 写失败测试（追加到 test_phase2cd.py）**

```python
# ---- build_portfolio_summary ----

from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position


def _insert_positions(settings: Settings, positions: list[Position]) -> None:
    create_all_tables(settings)
    with get_session(settings) as session:
        for p in positions:
            session.add(p)
        session.commit()


def test_build_portfolio_summary_mixed_currencies(tmp_path) -> None:
    """USDT + CNY 持仓，折算结果正确，breakdown 按市场分组。"""
    import hiveflow.infrastructure.fx_rate_provider as fx_mod
    from hiveflow.application.portfolio import build_portfolio_summary

    settings = Settings(database_url=f"sqlite:///{tmp_path}/p.db", cny_usdt_rate=7.0)
    _insert_positions(settings, [
        Position(symbol="BTC", quantity=0.1, market_value=8000.0, weight=0.0,
                 market="crypto", currency="USDT"),
        Position(symbol="000001.SZ", quantity=100.0, market_value=12500.0, weight=0.0,
                 market="cn_a_share", currency="CNY"),
    ])

    # mock FxRateProvider 返回 7.0
    mock_ak = MagicMock()
    mock_ak.currency_boc_sina.return_value = __import__("pandas").DataFrame(
        {"中行折算价": ["7.0"]}
    )
    original = fx_mod.akshare
    fx_mod.akshare = mock_ak
    try:
        summary = build_portfolio_summary(settings)
    finally:
        fx_mod.akshare = original

    # BTC: 8000 USDT → 56000 CNY
    # 000001: 12500 CNY → 12500/7 ≈ 1785.7 USDT
    assert abs(summary.total_usdt - (8000.0 + 12500.0 / 7.0)) < 1.0
    assert abs(summary.total_cny - (8000.0 * 7.0 + 12500.0)) < 1.0
    assert summary.fx_rate == 7.0
    assert summary.fx_source == "akshare"
    assert "crypto" in summary.breakdown
    assert "cn_a_share" in summary.breakdown
    assert summary.breakdown["crypto"]["currency"] == "USDT"
    assert summary.breakdown["cn_a_share"]["currency"] == "CNY"
    # 所有 weight_global 之和 ≈ 1.0
    total_weight = sum(p.weight_global for p in summary.positions)
    assert abs(total_weight - 1.0) < 0.01


def test_build_portfolio_summary_empty(tmp_path) -> None:
    """无持仓时返回合法的零值 PortfolioSummary，不报错。"""
    settings = Settings(database_url=f"sqlite:///{tmp_path}/empty.db")
    create_all_tables(settings)
    from hiveflow.application.portfolio import build_portfolio_summary
    summary = build_portfolio_summary(settings)
    assert summary.total_usdt == 0.0
    assert summary.total_cny == 0.0
    assert summary.positions == []
    assert summary.breakdown == {}


def test_build_portfolio_summary_breakdown_weights_sum_to_one(tmp_path) -> None:
    """breakdown 中所有 weight 之和 == 1.0（当有持仓时）。"""
    settings = Settings(database_url=f"sqlite:///{tmp_path}/p.db", cny_usdt_rate=7.25)
    _insert_positions(settings, [
        Position(symbol="BTC", quantity=0.5, market_value=30000.0, weight=0.0,
                 market="crypto", currency="USDT"),
        Position(symbol="ETH", quantity=5.0, market_value=10000.0, weight=0.0,
                 market="crypto", currency="USDT"),
    ])
    from hiveflow.application.portfolio import build_portfolio_summary
    summary = build_portfolio_summary(settings)
    total_breakdown_weight = sum(v["weight"] for v in summary.breakdown.values())
    assert abs(total_breakdown_weight - 1.0) < 0.01
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_phase2cd.py::test_build_portfolio_summary_mixed_currencies -v
```

Expected: FAIL — `portfolio` 模块不存在。

- [ ] **Step 3: 实现 build_portfolio_summary**

新建 `src/hiveflow/application/portfolio.py`：

```python
# src/hiveflow/application/portfolio.py
"""跨市场组合汇总：CNY/USDT 双货币折算视图。"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.fx_rate_provider import FxRateProvider


@dataclass
class PositionWithFx:
    symbol: str
    market: str           # "crypto" | "cn_a_share"
    currency: str         # "USDT" | "CNY"
    quantity: float
    market_value: float           # 原始货币金额
    market_value_usdt: float      # 折算为 USDT
    market_value_cny: float       # 折算为 CNY
    weight_global: float          # 占全局总 USDT 的比例（0-1）


@dataclass
class PortfolioSummary:
    positions: list[PositionWithFx] = field(default_factory=list)
    total_usdt: float = 0.0
    total_cny: float = 0.0
    fx_rate: float = 7.25         # 1 USDT = ? CNY
    fx_source: str = "config_fallback"
    breakdown: dict[str, dict] = field(default_factory=dict)
    # breakdown 结构: {"crypto": {"weight": 0.91, "value": 16600.0, "currency": "USDT"}, ...}


def build_portfolio_summary(settings: Settings | None = None) -> PortfolioSummary:
    """从数据库读所有 Position，折算为 CNY/USDT 双货币视图。

    折算规则：
    - currency="USDT": market_value_usdt = market_value; market_value_cny = market_value * fx_rate
    - currency="CNY":  market_value_cny  = market_value; market_value_usdt = market_value / fx_rate

    空持仓时返回 PortfolioSummary(positions=[], total_usdt=0, total_cny=0, breakdown={})。
    """
    s = settings or Settings()
    create_all_tables(s)

    # 1. 获取汇率
    fx_provider = FxRateProvider(s)
    fx_rate, fx_source = fx_provider.get_cny_per_usdt()

    # 2. 读取所有持仓
    with get_session(s) as session:
        positions = list(session.exec(select(Position)).all())

    if not positions:
        return PortfolioSummary(fx_rate=fx_rate, fx_source=fx_source)

    # 3. 折算
    fx_positions: list[PositionWithFx] = []
    for p in positions:
        if p.currency == "CNY":
            mv_cny = p.market_value
            mv_usdt = p.market_value / fx_rate if fx_rate > 0 else 0.0
        else:  # 默认 USDT
            mv_usdt = p.market_value
            mv_cny = p.market_value * fx_rate
        fx_positions.append(PositionWithFx(
            symbol=p.symbol,
            market=p.market,
            currency=p.currency,
            quantity=p.quantity,
            market_value=p.market_value,
            market_value_usdt=mv_usdt,
            market_value_cny=mv_cny,
            weight_global=0.0,  # 先占位，下面算
        ))

    # 4. 计算全局 weight（基于 USDT）
    total_usdt = sum(p.market_value_usdt for p in fx_positions)
    total_cny = sum(p.market_value_cny for p in fx_positions)
    for p in fx_positions:
        p.weight_global = p.market_value_usdt / total_usdt if total_usdt > 0 else 0.0

    # 5. breakdown 按 market 分组，本位货币展示
    breakdown: dict[str, dict] = {}
    for p in fx_positions:
        mkt = p.market
        native_currency = "USDT" if p.currency == "USDT" else "CNY"
        if mkt not in breakdown:
            breakdown[mkt] = {"weight": 0.0, "value": 0.0, "currency": native_currency}
        breakdown[mkt]["value"] += (
            p.market_value_usdt if native_currency == "USDT" else p.market_value_cny
        )
        breakdown[mkt]["weight"] += p.weight_global

    return PortfolioSummary(
        positions=fx_positions,
        total_usdt=total_usdt,
        total_cny=total_cny,
        fx_rate=fx_rate,
        fx_source=fx_source,
        breakdown=breakdown,
    )
```

- [ ] **Step 4: 运行新测试**

```bash
uv run python -m pytest tests/test_phase2cd.py -k "portfolio_summary" -v
```

Expected: 3 passed。

- [ ] **Step 5: 全量回归**

```bash
uv run python -m pytest -q
```

Expected: 438+ passed，0 failed。

- [ ] **Step 6: Commit**

```bash
git add src/hiveflow/application/portfolio.py tests/test_phase2cd.py
git commit -m "feat: 新增 build_portfolio_summary 跨市场货币折算应用层"
```

---

### Task 5: CLI — positions list 加折算列 + portfolio summary 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_phase2cd.py`（追加）

**背景：**
- `positions list` 命令在 `src/hiveflow/cli.py` 中，找到 `@positions_app.command("list")` 处
- 现有表格用 Rich 渲染，已有 `market_value` 列；需新增 `市值(USDT)`、`市值(CNY)`、`占比（全局）` 三列，底部加合计行和汇率说明
- 新增 `portfolio_app = typer.Typer(name="portfolio")` 子命令组，注册到 `app`，添加 `summary` 命令

- [ ] **Step 1: 写失败测试（追加到 test_phase2cd.py）**

```python
# ---- CLI ----

from typer.testing import CliRunner as TCliRunner
from hiveflow.cli import app as hiveflow_app


def _make_summary_mock():
    """创建一个完整的 PortfolioSummary mock 对象。"""
    from hiveflow.application.portfolio import PortfolioSummary, PositionWithFx
    return PortfolioSummary(
        positions=[
            PositionWithFx(symbol="BTC", market="crypto", currency="USDT",
                           quantity=0.12, market_value=8400.0,
                           market_value_usdt=8400.0, market_value_cny=60900.0,
                           weight_global=0.83),
            PositionWithFx(symbol="000001.SZ", market="cn_a_share", currency="CNY",
                           quantity=1000.0, market_value=12500.0,
                           market_value_usdt=1724.1, market_value_cny=12500.0,
                           weight_global=0.17),
        ],
        total_usdt=10124.1,
        total_cny=73400.0,
        fx_rate=7.25,
        fx_source="akshare",
        breakdown={
            "crypto":     {"weight": 0.83, "value": 8400.0,  "currency": "USDT"},
            "cn_a_share": {"weight": 0.17, "value": 12500.0, "currency": "CNY"},
        },
    )


def test_cli_portfolio_summary_text(tmp_path, monkeypatch) -> None:
    """portfolio summary 文本输出含总值、汇率来源、市场分布。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/p.db")
    with patch("hiveflow.cli.build_portfolio_summary", return_value=_make_summary_mock()):
        result = TCliRunner().invoke(hiveflow_app, ["portfolio", "summary"])
    assert result.exit_code == 0, result.stdout
    out = result.stdout
    assert "10,124" in out or "10124" in out   # total_usdt
    assert "73,400" in out or "73400" in out   # total_cny
    assert "7.25" in out
    assert "akshare" in out
    assert "crypto" in out
    assert "cn_a_share" in out
    assert "USDT" in out
    assert "CNY" in out


def test_cli_portfolio_summary_json(tmp_path, monkeypatch) -> None:
    """portfolio summary --output json 输出合法 JSON，含所有字段。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/p.db")
    with patch("hiveflow.cli.build_portfolio_summary", return_value=_make_summary_mock()):
        result = TCliRunner().invoke(hiveflow_app, ["portfolio", "summary", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "total_usdt" in payload
    assert "total_cny" in payload
    assert "fx_rate" in payload
    assert "fx_source" in payload
    assert "breakdown" in payload
    assert "positions" in payload
    assert payload["fx_rate"] == 7.25
    assert payload["fx_source"] == "akshare"


def test_cli_positions_list_fx_columns(tmp_path, monkeypatch) -> None:
    """positions list 输出包含 市值(CNY) 列和汇率行。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/p.db")
    with patch("hiveflow.cli.build_portfolio_summary", return_value=_make_summary_mock()):
        result = TCliRunner().invoke(hiveflow_app, ["positions", "list"])
    assert result.exit_code == 0, result.stdout
    assert "CNY" in result.stdout or "市值" in result.stdout
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_phase2cd.py::test_cli_portfolio_summary_text -v
```

Expected: FAIL — `portfolio` 命令不存在。

- [ ] **Step 3: 在 cli.py 中添加 portfolio_app 和导入**

打开 `src/hiveflow/cli.py`，在文件顶部的导入区（找到其他 `from hiveflow.application` 导入的地方）加：

```python
from hiveflow.application.portfolio import build_portfolio_summary, PortfolioSummary
```

在 `app = typer.Typer(...)` 定义处附近（找到其他 `xxx_app = typer.Typer(...)` 的地方），加：

```python
portfolio_app = typer.Typer(name="portfolio", help="跨市场组合视图（CNY/USDT 双货币）")
app.add_typer(portfolio_app)
```

- [ ] **Step 4: 实现 portfolio summary 命令**

在 cli.py 中，找到合适位置（`positions_app` 命令组附近），加：

```python
@portfolio_app.command("summary")
def portfolio_summary_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """跨市场组合汇总：虚拟币（USDT）+ A 股（CNY）统一视图。"""
    summary = build_portfolio_summary()

    if output == "json":
        payload = {
            "total_usdt": summary.total_usdt,
            "total_cny": summary.total_cny,
            "fx_rate": summary.fx_rate,
            "fx_source": summary.fx_source,
            "breakdown": summary.breakdown,
            "positions": [
                {
                    "symbol": p.symbol,
                    "market": p.market,
                    "currency": p.currency,
                    "market_value_usdt": round(p.market_value_usdt, 2),
                    "market_value_cny": round(p.market_value_cny, 2),
                    "weight_global": round(p.weight_global, 6),
                }
                for p in summary.positions
            ],
        }
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return

    # 文本输出
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("指标", style="bold cyan", min_width=18)
    table.add_column("数值", min_width=16)

    def _fmt_num(v: float, decimals: int = 0) -> str:
        return f"{v:,.{decimals}f}"

    table.add_row("总资产（USDT）", _fmt_num(summary.total_usdt))
    table.add_row("总资产（CNY）",  _fmt_num(summary.total_cny))
    table.add_row("汇率",          f"{summary.fx_rate}  ({summary.fx_source})")
    console.print(table)

    if summary.breakdown:
        console.print("\n[bold]市场分布[/bold]")
        for market_name, info in summary.breakdown.items():
            pct = f"{info['weight'] * 100:.0f}%"
            val = f"{info['value']:,.0f} {info['currency']}"
            console.print(f"  {market_name:<14} : {pct:>4}  {val}")
```

- [ ] **Step 5: 升级 positions list 命令加折算列**

`positions list` 命令在 `src/hiveflow/cli.py` 约 2450 行处（`@positions_app.command("list")`）。

**注意：JSON 输出分支不变**（`output == "json"` 分支 return early，不加折算列）。只修改 pretty 输出分支。

**5a. 在 pretty 分支开头（找到 `positions = list_positions()` 调用之后）加折算数据获取：**

```python
    # 拉取折算数据（用于显示，失败不中断）
    try:
        _summary = build_portfolio_summary()
        _fx_by_symbol = {p.symbol: p for p in _summary.positions}
        _fx_info = f"{_summary.fx_rate} ({_summary.fx_source})"
    except Exception:
        _fx_by_symbol = {}
        _fx_info = "N/A"
```

**5b. minimal 主题分支**（约 cli.py:2489）— 在 4 个 `add_column` 之后追加 3 列：

```python
        free_table.add_column("市值(USDT)", justify="right")
        free_table.add_column("市值(CNY)",  justify="right")
        free_table.add_column("全局占比",   justify="right")
```

**5c. hacker 主题分支**（约 cli.py:2501）— 同样追加 3 列（带颜色）：

```python
        free_table.add_column("市值(USDT)", justify="right", style="#5f875f")
        free_table.add_column("市值(CNY)",  justify="right", style="#5f875f")
        free_table.add_column("全局占比",   justify="right", style="#5f875f")
```

**5d. 修改 `add_row` 调用**（两个主题共用同一个 `for position in positions:` 循环，约 cli.py:2505）：

将原来的：
```python
        free_table.add_row(
            position.symbol,
            f"{position.quantity:.6f}",
            f"{position.market_value:.2f}",
            f"{position.weight:.2%}",
        )
```
改为：
```python
        fx_p = _fx_by_symbol.get(position.symbol)
        mv_usdt = f"{fx_p.market_value_usdt:,.0f}" if fx_p else "—"
        mv_cny  = f"{fx_p.market_value_cny:,.0f}"  if fx_p else "—"
        wt_str  = f"{fx_p.weight_global * 100:.1f}%" if fx_p else "—"
        free_table.add_row(
            position.symbol,
            f"{position.quantity:.6f}",
            f"{position.market_value:.2f}",
            f"{position.weight:.2%}",
            mv_usdt,
            mv_cny,
            wt_str,
        )
```

**5e. 在 `console.print(free_table)` 之后加汇率说明：**

```python
    console.print(f"[dim]汇率: {_fx_info}[/dim]")
```

- [ ] **Step 6: 运行新 CLI 测试**

```bash
uv run python -m pytest tests/test_phase2cd.py -k "cli" -v
```

Expected: 3 passed。

- [ ] **Step 7: 手动验证（可选，需有持仓数据）**

```bash
uv run hiveflow portfolio summary
uv run hiveflow portfolio summary --output json
uv run hiveflow positions list
```

- [ ] **Step 8: 全量回归**

```bash
uv run python -m pytest -q
```

Expected: 441+ passed，0 failed。

- [ ] **Step 9: Commit**

```bash
git add src/hiveflow/cli.py tests/test_phase2cd.py
git commit -m "feat: positions list 加折算列，新增 portfolio summary 命令"
```
