# A 股支持 Phase 1 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不破坏现有加密功能的前提下，加入 A 股持仓管理与行情分析能力（自动拉取 + 分析，交易手动）。

**Architecture:** 纯加法原则，OKX 路径不动。新增 `domain/market.py`（detect_market）、`domain/providers.py`（ABCs）、`infrastructure/cn_market_data_provider.py`、`application/cn_sync.py`；6 个实体加 `market` 字段；风险引擎与信号系统改为 market-aware。

**Tech Stack:** Python 3.12, typer, SQLModel, pandas, pytest, uv; akshare/tushare 为可选依赖

**前置依赖：** `docs/superpowers/plans/2026-03-23-signal-explicit-symbol-refactor.md` 必须先执行完毕（`build_signal_snapshot(symbol: str)` 接受显式 symbol 后，Chunk 5 才能正确落地）

---

## 文件地图

| 动作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/hiveflow/domain/market.py` | detect_market, CRYPTO/CN_A_SHARE 常量, ANNUALIZATION_FACTOR |
| 新建 | `src/hiveflow/domain/providers.py` | MarketDataProvider / PositionProvider ABCs（Clean Arch domain 层）|
| 新建 | `src/hiveflow/infrastructure/cn_market_data_provider.py` | CNMarketDataProvider（akshare/tushare 双后端）|
| 新建 | `src/hiveflow/application/cn_sync.py` | sync_cn_market_data（拉取并落库）|
| 新建 | `tests/test_market_detection.py` | detect_market 单元测试 |
| 新建 | `tests/test_cn_provider.py` | CNMarketDataProvider mock 测试 |
| 新建 | `tests/test_cn_positions.py` | import_cn_positions_from_csv + cn_sync 集成测试 |
| 修改 | `src/hiveflow/domain/market_data.py` | 加 market 字段 |
| 修改 | `src/hiveflow/domain/positions.py` | 加 market 字段 |
| 修改 | `src/hiveflow/domain/allocations.py` | TargetAllocation 加 market 字段 |
| 修改 | `src/hiveflow/domain/risk.py` | RiskSignal 加 market 字段 |
| 修改 | `src/hiveflow/domain/strategy_runs.py` | StrategyRun 加 market 字段 |
| 修改 | `src/hiveflow/domain/signal_snapshots.py` | SignalSnapshot 加 market 字段 |
| 修改 | `src/hiveflow/db.py` | _run_lightweight_migrations 追加 6 个 ALTER TABLE |
| 修改 | `src/hiveflow/config.py` | 新增 cn_market_data_source / tushare_token |
| 修改 | `pyproject.toml` | 新增 cn 可选依赖组（akshare, tushare） |
| 修改 | `src/hiveflow/application/positions.py` | 新增 import_cn_positions_from_csv |
| 修改 | `src/hiveflow/services/risk_engine.py` | compute_volatility / compute_portfolio_risk 加 annualization_factor 参数 |
| 修改 | `src/hiveflow/application/risk_analysis.py` | 调用时传 market-aware annualization_factor |
| 修改 | `src/hiveflow/application/signals.py` | 新增 SIGNAL_PARAMS，market-aware 参数分发，market 字段落库 |
| 修改 | `src/hiveflow/application/system.py` | doctor 新增 A 股依赖检查项 |
| 修改 | `src/hiveflow/application/summary.py` | get_summary_stats 支持 market 过滤；新增 get_market_summary |
| 修改 | `src/hiveflow/cli.py` | 新增 positions import-csv / market-data sync / summary --market；已有命令加 --market 过滤 |

---

## Chunk 1: Foundation — market 常量、Provider ABCs、实体迁移、配置

### Task 1: 新建 `domain/market.py`

**Files:**
- Create: `src/hiveflow/domain/market.py`
- Create: `tests/test_market_detection.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_market_detection.py
"""detect_market 单元测试。"""
import pytest
from hiveflow.domain.market import CN_A_SHARE, CRYPTO, ANNUALIZATION_FACTOR, detect_market


def test_detect_market_cn_sh() -> None:
    assert detect_market("600000.SH") == CN_A_SHARE


def test_detect_market_cn_sz() -> None:
    assert detect_market("000001.SZ") == CN_A_SHARE


def test_detect_market_cn_bj() -> None:
    assert detect_market("830017.BJ") == CN_A_SHARE


def test_detect_market_case_insensitive() -> None:
    assert detect_market("600000.sh") == CN_A_SHARE


def test_detect_market_cn_with_whitespace() -> None:
    assert detect_market("  000001.SZ  ") == CN_A_SHARE


def test_detect_market_crypto_btc() -> None:
    assert detect_market("BTC") == CRYPTO


def test_detect_market_crypto_eth() -> None:
    assert detect_market("ETH") == CRYPTO


def test_detect_market_no_suffix() -> None:
    """6 位数字但没有 .SH/.SZ/.BJ 后缀 → crypto（不是 A 股）"""
    assert detect_market("000001") == CRYPTO


def test_detect_market_empty_string() -> None:
    assert detect_market("") == CRYPTO


def test_detect_market_does_not_raise_on_garbage() -> None:
    assert detect_market("!@#$%") == CRYPTO


def test_annualization_factor_crypto() -> None:
    assert ANNUALIZATION_FACTOR[CRYPTO] == 365


def test_annualization_factor_cn() -> None:
    assert ANNUALIZATION_FACTOR[CN_A_SHARE] == 252
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_market_detection.py -v
```
Expected: ImportError（`domain/market.py` 不存在）

- [ ] **Step 3: 实现 `domain/market.py`**

```python
# src/hiveflow/domain/market.py
"""市场常量与 symbol 自动检测。"""
from __future__ import annotations

import re

CRYPTO = "crypto"
CN_A_SHARE = "cn_a_share"

ANNUALIZATION_FACTOR: dict[str, int] = {
    CRYPTO: 365,
    CN_A_SHARE: 252,
}

TRADING_DAYS: dict[str, int] = {
    CRYPTO: 365,
    CN_A_SHARE: 252,
}

_CN_SYMBOL_RE = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")


def detect_market(symbol: str) -> str:
    """根据 symbol 格式自动判断市场。

    000001.SZ / 600000.SH / 830017.BJ → cn_a_share
    其他（BTC、ETH、空字符串、垃圾格式）→ crypto
    """
    cleaned = symbol.strip().upper()
    if _CN_SYMBOL_RE.match(cleaned):
        return CN_A_SHARE
    return CRYPTO
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_market_detection.py -v
```
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/domain/market.py tests/test_market_detection.py
git commit -m "feat: 新增 domain/market.py，detect_market 与市场常量"
```

---

### Task 2: 新建 `domain/providers.py`

**Files:**
- Create: `src/hiveflow/domain/providers.py`

（无独立测试：ABCs 是纯接口，测试在具体实现处覆盖）

- [ ] **Step 1: 实现**

```python
# src/hiveflow/domain/providers.py
"""市场数据与持仓提供者抽象接口（Clean Architecture domain 层）。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """行情数据提供者接口。"""

    @abstractmethod
    def fetch_bars(self, symbols: list[str], days: int) -> list:
        """拉取最近 days 天的 OHLCV 行情，返回 MarketBar 列表。"""
        ...


class PositionProvider(ABC):
    """持仓数据提供者接口（面向长期连接的持仓同步，如券商 API）。"""

    @abstractmethod
    def fetch_positions(self) -> list:
        """返回当前账户持仓列表。"""
        ...
```

- [ ] **Step 2: 验证可导入**

```bash
uv run python -c "from hiveflow.domain.providers import MarketDataProvider, PositionProvider; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/hiveflow/domain/providers.py
git commit -m "feat: 新增 domain/providers.py，MarketDataProvider / PositionProvider ABCs"
```

---

### Task 3: 6 个实体加 `market` 字段 + db.py 迁移

**Files:**
- Modify: `src/hiveflow/domain/market_data.py`
- Modify: `src/hiveflow/domain/positions.py`
- Modify: `src/hiveflow/domain/allocations.py`
- Modify: `src/hiveflow/domain/risk.py`
- Modify: `src/hiveflow/domain/strategy_runs.py`
- Modify: `src/hiveflow/domain/signal_snapshots.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_market_detection.py`（追加迁移测试）

- [ ] **Step 1: 写迁移测试（追加到已有测试文件）**

```python
# tests/test_market_detection.py — 在文件末尾追加

import os
import tempfile
from pathlib import Path


def test_lightweight_migration_adds_market_to_position(tmp_path: Path) -> None:
    """旧库（无 market 列）在迁移后可正常读写，存量数据 market 默认 'crypto'。"""
    db_path = tmp_path / "hiveflow.db"
    db_url = f"sqlite:///{db_path}"

    # 用 SQLite 直接建一张模拟旧 position 表（无 market 列）
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE position (id INTEGER PRIMARY KEY, symbol TEXT, "
        "quantity REAL DEFAULT 0, market_value REAL DEFAULT 0, weight REAL DEFAULT 0, "
        "updated_at TEXT)"
    )
    conn.execute("INSERT INTO position (symbol) VALUES ('BTC')")
    conn.commit()
    conn.close()

    from hiveflow.config import Settings
    settings = Settings(database_url=db_url)
    from hiveflow.db import create_all_tables
    create_all_tables(settings)

    # 迁移后 market 列存在，旧行默认为 'crypto'
    conn2 = sqlite3.connect(str(db_path))
    row = conn2.execute(
        "SELECT market FROM position WHERE symbol='BTC'"
    ).fetchone()
    conn2.close()
    assert row is not None
    assert row[0] == "crypto"


def test_new_position_market_field_readable(tmp_path: Path) -> None:
    """新写入的 Position 可以读出 market 字段。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    with get_session(settings) as session:
        session.add(Position(symbol="000001.SZ", quantity=100, market_value=1000, weight=0.1, market="cn_a_share"))
        session.commit()

    with get_session(settings) as session:
        pos = session.exec(select(Position).where(Position.symbol == "000001.SZ")).first()
    assert pos is not None
    assert pos.market == "cn_a_share"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_market_detection.py::test_lightweight_migration_adds_market_to_position tests/test_market_detection.py::test_new_position_market_field_readable -v
```
Expected: FAIL（`market` 字段不存在）

- [ ] **Step 3: 修改 6 个实体，加 `market` 字段**

**`src/hiveflow/domain/market_data.py`** — 在 `volume: float` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

**`src/hiveflow/domain/positions.py`** — 在 `updated_at` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

**`src/hiveflow/domain/allocations.py`** — 在 `TargetAllocation` 的 `generated_at` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

**`src/hiveflow/domain/risk.py`** — 在 `RiskSignal` 的 `calculated_at` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

**`src/hiveflow/domain/strategy_runs.py`** — 在 `StrategyRun` 的 `run_at` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

**`src/hiveflow/domain/signal_snapshots.py`** — 在 `created_at` 后加：
```python
    # 市场标识：crypto / cn_a_share。
    market: str = "crypto"
```

- [ ] **Step 4: 修改 `db.py`，在 `_run_lightweight_migrations` 末尾追加 6 个迁移块**

在现有 `stylebacktestresult` 迁移块结束后追加（紧接在最后一个 `if "stylebacktestresult"` 块的关闭括号之后）：

```python
        # market 字段迁移：适用于 position / marketbar / targetallocation /
        # risksignal / strategyrun / signalsnapshot 表
        _market_tables = [
            "position",
            "marketbar",
            "targetallocation",
            "risksignal",
            "strategyrun",
            "signalsnapshot",
        ]
        for _tbl in _market_tables:
            if _tbl in tables:
                _cols = conn.exec_driver_sql(f"PRAGMA table_info('{_tbl}')").fetchall()
                _col_names = {row[1] for row in _cols}
                if "market" not in _col_names:
                    conn.exec_driver_sql(
                        f"ALTER TABLE {_tbl} ADD COLUMN market VARCHAR DEFAULT 'crypto'"
                    )
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_market_detection.py -v
```
Expected: 全部通过（14 passed）

- [ ] **Step 6: 全量回归**

```bash
uv run python -m pytest -q
```
Expected: 280+ passed, 0 failed

- [ ] **Step 7: Commit**

```bash
git add src/hiveflow/domain/market_data.py src/hiveflow/domain/positions.py \
        src/hiveflow/domain/allocations.py src/hiveflow/domain/risk.py \
        src/hiveflow/domain/strategy_runs.py src/hiveflow/domain/signal_snapshots.py \
        src/hiveflow/db.py tests/test_market_detection.py
git commit -m "feat: 6 个实体加 market 字段，db.py 新增轻量迁移"
```

---

### Task 4: config.py + pyproject.toml

**Files:**
- Modify: `src/hiveflow/config.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: 修改 `config.py`，在现有 OKX 配置后追加**

```python
    # A 股行情数据源（env: HIVEFLOW_CN_MARKET_DATA_SOURCE）
    cn_market_data_source: str = "akshare"  # "akshare" | "tushare"
    # Tushare token（env: HIVEFLOW_TUSHARE_TOKEN，cn_market_data_source=tushare 时必填）
    tushare_token: str = ""
```

- [ ] **Step 2: 修改 `pyproject.toml`，在 `[project.optional-dependencies]` 中追加**

在现有 `dev = [...]` 后加：

```toml
cn = [
  "akshare>=1.14.0",
  "tushare>=1.4.0",
]
```

- [ ] **Step 3: 验证配置可读取**

```bash
uv run python -c "from hiveflow.config import Settings; s=Settings(); print(s.cn_market_data_source, s.tushare_token)"
```
Expected: `akshare `

- [ ] **Step 4: Commit**

```bash
git add src/hiveflow/config.py pyproject.toml
git commit -m "feat: config 新增 cn_market_data_source / tushare_token，pyproject 新增 cn 可选依赖"
```

---

## Chunk 2: Infrastructure + Application — CN 行情同步

### Task 5: `infrastructure/cn_market_data_provider.py`

**Files:**
- Create: `src/hiveflow/infrastructure/cn_market_data_provider.py`
- Create: `tests/test_cn_provider.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cn_provider.py
"""CNMarketDataProvider mock 测试（不依赖真实外部 API）。"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.domain.market import CN_A_SHARE


def _make_akshare_df(symbol: str):
    """构造 akshare fund_etf_hist_em 返回的 DataFrame 格式。"""
    import pandas as pd
    return pd.DataFrame({
        "日期": ["2026-01-01", "2026-01-02"],
        "开盘": [10.0, 10.5],
        "最高": [10.8, 11.0],
        "最低": [9.9, 10.3],
        "收盘": [10.5, 10.8],
        "成交量": [1000000, 1200000],
    })


def test_cn_provider_akshare_returns_market_bars(tmp_path: Path) -> None:
    """akshare 后端返回 MarketBar 列表，market 字段为 cn_a_share。

    patch 路径为模块级属性 `hiveflow.infrastructure.cn_market_data_provider.akshare`，
    实现中通过 `_self_mod.akshare` 访问，使 mock 生效。
    """
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod

    mock_ak = MagicMock()
    mock_ak.stock_zh_a_hist.return_value = _make_akshare_df("000001")

    original = provider_mod.akshare
    provider_mod.akshare = mock_ak
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="akshare")
        bars = provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.akshare = original

    assert len(bars) == 2
    for bar in bars:
        assert bar.market == CN_A_SHARE
        assert bar.symbol == "000001.SZ"
        assert bar.close > 0


def test_cn_provider_tushare_returns_market_bars(tmp_path: Path) -> None:
    """tushare 后端返回相同格式的 MarketBar 列表。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod

    mock_df = pd.DataFrame({
        "trade_date": ["20260101", "20260102"],
        "open": [10.0, 10.5],
        "high": [10.8, 11.0],
        "low": [9.9, 10.3],
        "close": [10.5, 10.8],
        "vol": [1000000.0, 1200000.0],
    })
    mock_pro = MagicMock()
    mock_pro.daily.return_value = mock_df
    mock_ts = MagicMock()
    mock_ts.pro_api.return_value = mock_pro

    original = provider_mod.tushare
    provider_mod.tushare = mock_ts
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="tushare", token="fake_token")
        bars = provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.tushare = original

    assert len(bars) == 2
    for bar in bars:
        assert bar.market == CN_A_SHARE
        assert bar.symbol == "000001.SZ"


def test_cn_provider_unsupported_source_raises() -> None:
    """不支持的 source 在 fetch_bars 时应抛出 ValueError。"""
    from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
    provider = CNMarketDataProvider(source="unknown_source")
    with pytest.raises(ValueError, match="不支持的数据源"):
        provider.fetch_bars(["000001.SZ"], days=5)


def test_cn_provider_missing_akshare_raises_import_error() -> None:
    """模块级 akshare=None 时，fetch_bars 应抛出 ImportError 并提示安装方法。"""
    import hiveflow.infrastructure.cn_market_data_provider as provider_mod
    original = provider_mod.akshare
    provider_mod.akshare = None  # 模拟未安装
    try:
        from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider
        provider = CNMarketDataProvider(source="akshare")
        with pytest.raises(ImportError, match="akshare"):
            provider.fetch_bars(["000001.SZ"], days=5)
    finally:
        provider_mod.akshare = original
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_cn_provider.py -v
```
Expected: ImportError（文件不存在）

- [ ] **Step 3: 实现 `cn_market_data_provider.py`**

关键设计：akshare / tushare 在**模块级别**做 try/except 导入，使其成为可 patch 的模块属性，测试时可通过 `patch("hiveflow.infrastructure.cn_market_data_provider.akshare", ...)` 注入 mock。

```python
# src/hiveflow/infrastructure/cn_market_data_provider.py
"""A 股行情数据提供者（akshare / tushare 双后端）。"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from hiveflow.domain.market import CN_A_SHARE
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.providers import MarketDataProvider

# 模块级可选导入：使 akshare / tushare 成为可 patch 的模块属性
try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]

try:
    import tushare  # type: ignore[import]
except ImportError:
    tushare = None  # type: ignore[assignment]


class CNMarketDataProvider(MarketDataProvider):
    """A 股行情提供者，支持 akshare 和 tushare 两个后端，通过 source 参数切换。"""

    def __init__(self, source: str, token: str = "") -> None:
        self._source = source
        self._token = token

    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]:
        if self._source == "akshare":
            return self._fetch_via_akshare(symbols, days)
        elif self._source == "tushare":
            return self._fetch_via_tushare(symbols, days)
        else:
            raise ValueError(f"不支持的数据源: {self._source!r}，支持 'akshare' 或 'tushare'")

    # ------------------------------------------------------------------ #
    # akshare 后端
    # ------------------------------------------------------------------ #

    def _fetch_via_akshare(self, symbols: list[str], days: int) -> list[MarketBar]:
        # 使用模块级 akshare 变量（支持 patch）
        import hiveflow.infrastructure.cn_market_data_provider as _self_mod
        _ak = _self_mod.akshare
        if _ak is None:
            raise ImportError(
                "akshare 未安装。请运行: uv pip install 'hiveflow[cn]' 或 pip install akshare"
            )
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=days)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        bars: list[MarketBar] = []
        for symbol in symbols:
            # akshare 期望 6 位代码（无交易所后缀）
            code = symbol.split(".")[0] if "." in symbol else symbol
            try:
                df = _ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust="qfq",  # 前复权
                )
            except Exception:
                continue  # 单个 symbol 失败不中断整批

            for _, row in df.iterrows():
                try:
                    ts = datetime.strptime(str(row["日期"]), "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                    bars.append(MarketBar(
                        symbol=symbol.upper(),
                        timestamp=ts,
                        open=float(row["开盘"]),
                        high=float(row["最高"]),
                        low=float(row["最低"]),
                        close=float(row["收盘"]),
                        volume=float(row["成交量"]),
                        market=CN_A_SHARE,
                    ))
                except (KeyError, ValueError):
                    continue
        return bars

    # ------------------------------------------------------------------ #
    # tushare 后端
    # ------------------------------------------------------------------ #

    def _fetch_via_tushare(self, symbols: list[str], days: int) -> list[MarketBar]:
        # 使用模块级 tushare 变量（支持 patch）
        import hiveflow.infrastructure.cn_market_data_provider as _self_mod
        _ts = _self_mod.tushare
        if _ts is None:
            raise ImportError(
                "tushare 未安装。请运行: uv pip install 'hiveflow[cn]' 或 pip install tushare"
            )
        pro = _ts.pro_api(self._token)
        end = datetime.now(tz=timezone.utc)
        start = end - timedelta(days=days)
        start_str = start.strftime("%Y%m%d")
        end_str = end.strftime("%Y%m%d")

        bars: list[MarketBar] = []
        for symbol in symbols:
            ts_code = symbol.upper()
            try:
                df = pro.daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
            except Exception:
                continue

            for _, row in df.iterrows():
                try:
                    ts_date = str(row["trade_date"])
                    ts_dt = datetime.strptime(ts_date, "%Y%m%d").replace(
                        tzinfo=timezone.utc
                    )
                    bars.append(MarketBar(
                        symbol=symbol.upper(),
                        timestamp=ts_dt,
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=float(row["vol"]),
                        market=CN_A_SHARE,
                    ))
                except (KeyError, ValueError):
                    continue
        return bars
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_cn_provider.py -v
```
Expected: 4 passed（missing_akshare 测试可能需要根据环境跳过，见备注）

> 备注：`test_cn_provider_missing_akshare_raises_import_error` 依赖 `importlib.reload`，若 akshare 未安装则直接 pass。若安装了 akshare，该测试通过 `sys.modules` 操作模拟未安装。

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/infrastructure/cn_market_data_provider.py tests/test_cn_provider.py
git commit -m "feat: 新增 CNMarketDataProvider（akshare/tushare 双后端）"
```

---

### Task 6: `application/cn_sync.py`

**Files:**
- Create: `src/hiveflow/application/cn_sync.py`
- Create: `tests/test_cn_positions.py`（第一批测试）

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cn_positions.py
"""A 股行情同步与持仓导入测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.domain.market import CN_A_SHARE


# ------------------------------------------------------------------ #
# Chunk 2 Task 6 — cn_sync
# ------------------------------------------------------------------ #

def _fake_bars(symbol: str = "000001.SZ"):
    from datetime import datetime, timezone
    from hiveflow.domain.market_data import MarketBar
    return [
        MarketBar(
            symbol=symbol,
            timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            open=10.0 + i,
            high=11.0 + i,
            low=9.0 + i,
            close=10.5 + i,
            volume=1_000_000.0,
            market=CN_A_SHARE,
        )
        for i in range(3)
    ]


def test_sync_cn_market_data_writes_bars_to_db(tmp_path: Path) -> None:
    """sync_cn_market_data 应将 MarketBar 写入数据库。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="akshare")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars("000001.SZ")

    with patch(
        "hiveflow.application.cn_sync.CNMarketDataProvider",
        return_value=fake_provider,
    ):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(
            symbols=["000001.SZ"], days=30, settings=settings
        )

    assert result.imported == 3
    assert result.symbols == ["000001.SZ"]

    with get_session(settings) as session:
        bars = session.exec(
            select(MarketBar).where(MarketBar.symbol == "000001.SZ")
        ).all()
    assert len(bars) == 3
    assert all(b.market == CN_A_SHARE for b in bars)


def test_sync_cn_market_data_result_fields(tmp_path: Path) -> None:
    """result 包含 imported / symbols / source 字段。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url, cn_market_data_source="tushare", tushare_token="tok")
    create_all_tables(settings)

    fake_provider = MagicMock()
    fake_provider.fetch_bars.return_value = _fake_bars()

    with patch("hiveflow.application.cn_sync.CNMarketDataProvider", return_value=fake_provider):
        from hiveflow.application.cn_sync import sync_cn_market_data
        result = sync_cn_market_data(symbols=["000001.SZ"], days=7, settings=settings)

    assert result.source == "tushare"
    assert "000001.SZ" in result.symbols
    d = result.to_dict()
    assert "imported" in d
    assert "symbols" in d
    assert "source" in d
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_cn_positions.py::test_sync_cn_market_data_writes_bars_to_db tests/test_cn_positions.py::test_sync_cn_market_data_result_fields -v
```
Expected: ImportError（`cn_sync.py` 不存在）

- [ ] **Step 3: 实现 `application/cn_sync.py`**

```python
# src/hiveflow/application/cn_sync.py
"""A 股行情同步应用服务。"""
from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar
from hiveflow.infrastructure.cn_market_data_provider import CNMarketDataProvider


@dataclass(frozen=True)
class CNSyncResult:
    """A 股行情同步结果。"""
    imported: int
    symbols: list[str]
    source: str

    def to_dict(self) -> dict:
        return {
            "imported": self.imported,
            "symbols": self.symbols,
            "source": self.source,
        }


def sync_cn_market_data(
    symbols: list[str],
    days: int,
    settings: Settings | None = None,
) -> CNSyncResult:
    """使用 CNMarketDataProvider 拉取 A 股行情并写入 MarketBar 表。

    market 字段由 CNMarketDataProvider 自动填充为 'cn_a_share'。
    重复记录（同 symbol + timestamp）覆盖写入：先删除旧记录再插入。
    """
    s = settings or Settings()
    create_all_tables(s)

    provider = CNMarketDataProvider(source=s.cn_market_data_source, token=s.tushare_token)
    bars = provider.fetch_bars(symbols, days)

    with get_session(s) as session:
        for bar in bars:
            # 覆盖写入：删除相同 symbol + timestamp 的旧记录
            existing = session.exec(
                select(MarketBar).where(
                    MarketBar.symbol == bar.symbol,
                    MarketBar.timestamp == bar.timestamp,
                )
            ).all()
            for old in existing:
                session.delete(old)
            session.add(bar)
        session.commit()

    return CNSyncResult(
        imported=len(bars),
        symbols=symbols,
        source=s.cn_market_data_source,
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_cn_positions.py::test_sync_cn_market_data_writes_bars_to_db tests/test_cn_positions.py::test_sync_cn_market_data_result_fields -v
```
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/cn_sync.py tests/test_cn_positions.py
git commit -m "feat: 新增 application/cn_sync.py，sync_cn_market_data"
```

---

## Chunk 3: Application — CN 持仓导入

### Task 7: `application/positions.py` 新增 `import_cn_positions_from_csv`

**Files:**
- Modify: `src/hiveflow/application/positions.py`
- Modify: `tests/test_cn_positions.py`（追加测试）

- [ ] **Step 1: 追加失败测试到 `tests/test_cn_positions.py`**

```python
# tests/test_cn_positions.py — 在文件末尾追加

# ------------------------------------------------------------------ #
# Chunk 3 Task 7 — import_cn_positions_from_csv
# ------------------------------------------------------------------ #

def _write_csv(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_import_cn_positions_valid_csv(tmp_path: Path) -> None:
    """正常 CSV 导入后，Position.market == 'cn_a_share'。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from hiveflow.application.positions import import_cn_positions_from_csv
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "cn.csv",
        "symbol,quantity,avg_cost,market_value\n"
        "000001.SZ,1000,12.50,13200\n"
        "600000.SH,500,8.80,4600\n",
    )

    result = import_cn_positions_from_csv(str(csv_file), settings=settings)
    assert result.imported == 2

    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()
    symbols = {p.symbol for p in positions}
    assert "000001.SZ" in symbols
    assert "600000.SH" in symbols
    assert all(p.market == CN_A_SHARE for p in positions)


def test_import_cn_positions_duplicate_overwrite(tmp_path: Path) -> None:
    """重复导入同一 symbol 时覆盖写入，不重复堆积。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    from hiveflow.application.positions import import_cn_positions_from_csv
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv1 = _write_csv(tmp_path / "cn1.csv", "symbol,quantity,avg_cost,market_value\n000001.SZ,1000,12.50,13200\n")
    import_cn_positions_from_csv(str(csv1), settings=settings)

    csv2 = _write_csv(tmp_path / "cn2.csv", "symbol,quantity,avg_cost,market_value\n000001.SZ,2000,11.00,22000\n")
    import_cn_positions_from_csv(str(csv2), settings=settings)

    with get_session(settings) as session:
        rows = session.exec(select(Position).where(Position.symbol == "000001.SZ")).all()
    assert len(rows) == 1
    assert rows[0].quantity == 2000.0


def test_import_cn_positions_crypto_symbol_rejected(tmp_path: Path) -> None:
    """CSV 中包含 BTC（加密 symbol）时应报错拒绝导入。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    from hiveflow.application.positions import import_cn_positions_from_csv

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "bad.csv",
        "symbol,quantity,avg_cost,market_value\nBTC,0.5,50000,25000\n",
    )

    with pytest.raises(ValueError, match="非 A 股 symbol"):
        import_cn_positions_from_csv(str(csv_file), settings=settings)


def test_import_cn_positions_market_mismatch_rejected(tmp_path: Path) -> None:
    """CSV market 列与 detect_market 推断结果不一致时应报错。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    from hiveflow.application.positions import import_cn_positions_from_csv

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    csv_file = _write_csv(
        tmp_path / "mismatch.csv",
        "symbol,quantity,avg_cost,market_value,market\n"
        "000001.SZ,1000,12.50,13200,crypto\n",  # market 列与 symbol 不符
    )

    with pytest.raises(ValueError, match="market 字段不一致"):
        import_cn_positions_from_csv(str(csv_file), settings=settings)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_cn_positions.py -k "import_cn" -v
```
Expected: AttributeError（`import_cn_positions_from_csv` 不存在）

- [ ] **Step 3: 在 `application/positions.py` 末尾追加实现**

在文件最后 `export_positions_template` 函数之后追加：

```python
@dataclass(frozen=True)
class CNImportResult:
    imported: int
    file: str

    def to_dict(self) -> dict[str, int | str]:
        return {"imported": self.imported, "file": self.file}


def import_cn_positions_from_csv(
    file_path: str,
    settings=None,
) -> CNImportResult:
    """从 CSV 导入 A 股持仓。

    校验规则：
    1. symbol 必须匹配 detect_market(symbol) == CN_A_SHARE，否则抛 ValueError（非 A 股 symbol）
    2. CSV 的 market 列（若存在）必须与 detect_market 结果一致，否则抛 ValueError（market 字段不一致）
    3. 重复导入同一 symbol 则覆盖写入（先删除旧记录）

    CSV 格式（market 列可选）：
        symbol,quantity,avg_cost,market_value
        000001.SZ,1000,12.50,13200
    """
    from csv import DictReader
    from hiveflow.domain.market import CN_A_SHARE, detect_market
    from hiveflow.domain.positions import Position
    from sqlmodel import select

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV 文件不存在：{file_path}")

    create_all_tables(settings)

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = DictReader(f)
        required = {"symbol", "quantity", "market_value"}
        if not reader.fieldnames or not required.issubset(set(reader.fieldnames)):
            raise ValueError("CSV 列必须包含：symbol, quantity, market_value")

        rows = list(reader)

    validated: list[dict] = []
    for row in rows:
        sym = (row.get("symbol") or "").strip()
        inferred = detect_market(sym)
        if inferred != CN_A_SHARE:
            raise ValueError(
                f"非 A 股 symbol：{sym!r}（detect_market 返回 {inferred!r}），"
                "请确认 CSV 只包含 A 股标的（如 000001.SZ）"
            )
        if "market" in row and row["market"] and row["market"].strip() != CN_A_SHARE:
            raise ValueError(
                f"market 字段不一致：symbol={sym!r} 推断市场为 {CN_A_SHARE!r}，"
                f"但 CSV market 列为 {row['market']!r}"
            )
        validated.append(row)

    with get_session(settings) as session:
        for row in validated:
            sym = row["symbol"].strip().upper()
            # 覆盖写入：先删除同一 symbol 的旧记录
            existing = session.exec(
                select(Position).where(Position.symbol == sym).where(Position.market == CN_A_SHARE)
            ).all()
            for old in existing:
                session.delete(old)
            session.add(Position(
                symbol=sym,
                quantity=float(row["quantity"]),
                market_value=float(row["market_value"]),
                weight=0.0,  # 导入时权重后续由 drift/rebalance 计算
                market=CN_A_SHARE,
            ))
        session.commit()

    return CNImportResult(imported=len(validated), file=str(path))
```

注意：需要在文件顶部已有 import 块中确认 `from hiveflow.db import create_all_tables, get_session` 已存在（查看文件头部，已有则无需再加）。

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_cn_positions.py -k "import_cn" -v
```
Expected: 4 passed

- [ ] **Step 5: 全量回归**

```bash
uv run python -m pytest -q
```
Expected: 280+ passed, 0 failed

- [ ] **Step 6: Commit**

```bash
git add src/hiveflow/application/positions.py tests/test_cn_positions.py
git commit -m "feat: positions.py 新增 import_cn_positions_from_csv"
```

---

## Chunk 4: Risk Engine Market-Awareness

### Task 8: `services/risk_engine.py` + `application/risk_analysis.py`

**Files:**
- Modify: `src/hiveflow/services/risk_engine.py`
- Modify: `src/hiveflow/application/risk_analysis.py`
- Modify: `tests/test_risk_engine.py`（追加测试）

- [ ] **Step 1: 追加失败测试到 `tests/test_risk_engine.py`**

```python
# tests/test_risk_engine.py — 在文件末尾追加

def test_compute_volatility_with_cn_annualization() -> None:
    """传 annualization_factor=252 时，annual_vol == daily_vol × sqrt(252)。"""
    import math
    prices = {"000001.SZ": _make_bars("000001.SZ", [10.0, 10.5, 10.3, 10.8, 10.6])}
    results = compute_volatility(prices, annualization_factor=252)
    assert len(results) == 1
    v = results[0]
    assert abs(v.annual_vol - v.daily_vol * math.sqrt(252)) < 1e-9


def test_compute_volatility_default_is_365() -> None:
    """不传 annualization_factor 时默认 365（向后兼容）。"""
    import math
    prices = {"BTC": _make_bars("BTC", [100.0, 110.0, 105.0, 115.0, 110.0])}
    default_results = compute_volatility(prices)
    explicit_results = compute_volatility(prices, annualization_factor=365)
    assert abs(default_results[0].annual_vol - explicit_results[0].annual_vol) < 1e-12


def test_compute_portfolio_risk_with_cn_annualization() -> None:
    """传 annualization_factor=252 时，annual_vol 使用 252 年化。"""
    import math
    curve = [100.0, 102.0, 101.5, 103.0, 102.5, 104.0]
    result_365 = compute_portfolio_risk(curve, annualization_factor=365)
    result_252 = compute_portfolio_risk(curve, annualization_factor=252)
    # 252 年化的 annual_vol 应比 365 小
    assert result_252["annual_vol"] < result_365["annual_vol"]
    # 比例接近 sqrt(252/365)
    ratio = result_252["annual_vol"] / result_365["annual_vol"]
    assert abs(ratio - math.sqrt(252 / 365)) < 1e-9
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_risk_engine.py -k "annualization" -v
```
Expected: TypeError（`compute_volatility` 不接受 `annualization_factor` 参数）

- [ ] **Step 3: 修改 `risk_engine.py`**

**`compute_volatility`**：在函数签名加参数并替换硬编码 365：

```python
# 修改前：
def compute_volatility(prices: dict[str, list[PriceBar]]) -> list[AssetVolatility]:

# 修改后：
def compute_volatility(
    prices: dict[str, list[PriceBar]],
    annualization_factor: int = 365,
) -> list[AssetVolatility]:
```

函数体内将 `math.sqrt(365)` 替换为 `math.sqrt(annualization_factor)`（共 1 处）。

**`compute_portfolio_risk`**：

```python
# 修改前：
def compute_portfolio_risk(curve: list[float]) -> dict:

# 修改后：
def compute_portfolio_risk(curve: list[float], annualization_factor: int = 365) -> dict:
```

函数体内将 `math.sqrt(365)` 替换为 `math.sqrt(annualization_factor)`（共 1 处）。

- [ ] **Step 4: 修改 `application/risk_analysis.py`，传入 market-aware 因子**

在 `analyze_asset_risk` 函数中，找到 `prices = load_close_prices_from_db(...)` 之后的 `compute_volatility(prices)` 调用，在其上方插入：

```python
# 在 prices 非空校验之后（此时 symbols 已从 DB 或参数填充，非空）
from hiveflow.domain.market import ANNUALIZATION_FACTOR, detect_market

# 取第一个 symbol 的市场作为整批年化因子（同批 symbols 应为同市场）
ann_factor = ANNUALIZATION_FACTOR.get(detect_market(symbols[0]), 365)

vols = compute_volatility(prices, annualization_factor=ann_factor)
dds = compute_drawdown(prices)
```

注意：`ann_factor` 的插入点在 `if not prices: raise ValueError(...)` 之后、`vols = compute_volatility(prices)` 之前。此处 `symbols` 已经是填充完毕的非空列表（若 DB 查询返回空列表，上方的 ValueError 已终止函数），因此可安全取 `symbols[0]`。

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_risk_engine.py -v
```
Expected: 全部通过

- [ ] **Step 6: 全量回归**

```bash
uv run python -m pytest -q
```
Expected: 280+ passed, 0 failed

- [ ] **Step 7: Commit**

```bash
git add src/hiveflow/services/risk_engine.py src/hiveflow/application/risk_analysis.py tests/test_risk_engine.py
git commit -m "feat: risk_engine compute_volatility / compute_portfolio_risk 支持 annualization_factor 参数"
```

---

## Chunk 5: Signal System Market-Awareness

> **前提：** `signal-explicit-symbol-refactor` 计划已完成，`build_signal_snapshot(symbol: str)` 已接受显式 symbol 参数。

### Task 9: `application/signals.py` — SIGNAL_PARAMS + market 字段

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Modify: `src/hiveflow/domain/signal_snapshots.py`（已在 Task 3 加 market 字段）
- Modify: `tests/test_signal_cli.py`（追加测试）

- [ ] **Step 1: 追加失败测试到 `tests/test_signal_cli.py`**

```python
# tests/test_signal_cli.py — 在文件末尾追加

def test_signal_snapshot_cn_symbol_uses_cn_params(tmp_path, monkeypatch) -> None:
    """A 股 symbol 触发时，signal 输出应包含 market='cn_a_share'。"""
    # 需要先用 A 股行情数据 seed
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.domain.positions import Position
    from datetime import datetime, timezone

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    with get_session(settings) as session:
        for i in range(42):
            session.add(MarketBar(
                symbol="000001.SZ",
                timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                open=10.0 + i * 0.1,
                high=10.5 + i * 0.1,
                low=9.8 + i * 0.1,
                close=10.2 + i * 0.1,
                volume=1_000_000.0,
                market="cn_a_share",
            ))
        session.add(Position(symbol="000001.SZ", quantity=1000, market_value=10200, weight=1.0, market="cn_a_share"))
        session.commit()

    from hiveflow.application.signals import build_signal_snapshot
    payload = build_signal_snapshot("000001.SZ", settings=settings)
    assert payload["market"] == "cn_a_share"
    assert payload["symbol"] == "000001.SZ"


def test_signal_snapshot_cn_writes_market_to_db(tmp_path, monkeypatch) -> None:
    """build_signal_snapshot 落库后，SignalSnapshot.market == 'cn_a_share'。"""
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.domain.positions import Position
    from hiveflow.domain.signal_snapshots import SignalSnapshot
    from datetime import datetime, timezone
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    with get_session(settings) as session:
        for i in range(42):
            session.add(MarketBar(
                symbol="000001.SZ",
                timestamp=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
                open=10.0 + i * 0.1, high=10.5 + i * 0.1,
                low=9.8 + i * 0.1, close=10.2 + i * 0.1,
                volume=1_000_000.0, market="cn_a_share",
            ))
        session.add(Position(symbol="000001.SZ", quantity=1000, market_value=10200, weight=1.0, market="cn_a_share"))
        session.commit()

    from hiveflow.application.signal_snapshots import save_signal_snapshot
    from hiveflow.application.signals import build_signal_snapshot
    payload = build_signal_snapshot("000001.SZ", settings=settings)
    save_signal_snapshot(payload, settings=settings)

    with get_session(settings) as session:
        snap = session.exec(
            select(SignalSnapshot).where(SignalSnapshot.symbol == "000001.SZ")
        ).first()
    assert snap is not None
    assert snap.market == "cn_a_share"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py -k "cn_symbol or cn_writes_market" -v
```
Expected: FAIL（`build_signal_snapshot` 输出无 `market` 字段，或 `SignalSnapshot.market` 仍为默认 'crypto'）

- [ ] **Step 3: 修改 `application/signals.py`**

**3a.** 在 `SIGNALS_BY_CATEGORY` 定义之后添加 `SIGNAL_PARAMS`：

```python
from hiveflow.domain.market import CN_A_SHARE, CRYPTO, detect_market

SIGNAL_PARAMS: dict[str, dict[str, int]] = {
    CRYPTO:     {"ma_short": 7,  "ma_long": 30, "vol_window": 30},
    CN_A_SHARE: {"ma_short": 5,  "ma_long": 20, "vol_window": 20},
}
```

**3b.** 在 `build_signal_snapshot(symbol: str, ...)` 函数体内，`symbol = symbol.upper()` 之后、`_ensure_required_samples(...)` 之前，添加：

```python
    market = detect_market(symbol)
    _params = SIGNAL_PARAMS.get(market, SIGNAL_PARAMS[CRYPTO])
    _ma_short = _params["ma_short"]    # crypto=7, cn_a_share=5
    _ma_long  = _params["ma_long"]     # crypto=30, cn_a_share=20
    _vol_win  = _params["vol_window"]  # crypto=30, cn_a_share=20
```

**3c.** 将函数体内以下 4 处硬编码窗口替换为变量（已确认 `build_signal_snapshot` 实际代码，路径 `src/hiveflow/application/signals.py`）：

| 原始代码 | 替换为 |
|---------|--------|
| `close.tail(7).mean()` | `close.tail(_ma_short).mean()` |
| `close.tail(30).mean()` | `close.tail(_ma_long).mean()` |
| `close.iloc[-8:-1].mean()` | `close.iloc[-(_ma_short+1):-1].mean()` |
| `close.iloc[-31:-1].mean()` | `close.iloc[-(_ma_long+1):-1].mean()` |

以上 4 处均在 `# ── trend ──` 注释块下方，用于计算 `fast_cur / slow_cur / fast_prev / slow_prev`。其余信号计算（MACD、ATR、ADX 等）使用独立参数，**不在此次替换范围内**（Phase 1 保守策略：只替换 MA 交叉参数）。

`universe_symbols` 的 `>= 30` 阈值和 `_ensure_required_samples(required=40)` 的最低样本数**保持不变**：MACD 需要 26+9=35 样本，40 是安全边际，CN 参数不改 MACD，测试 fixture 用 42 条 bar 即可通过。

**3d.** 在 `build_signal_snapshot` 的 `return` dict 中加 `"market": market`：

```python
    return {
        "symbol": symbol,
        "market": market,   # ← 新增
        "as_of": ...,
        "signals": ...,
        ...
    }
```

- [ ] **Step 4: 修改 `application/signal_snapshots.py`（save_signal_snapshot）**

找到 `save_signal_snapshot(payload, ...)` 函数，在写入 `SignalSnapshot` 的地方加 `market` 字段：

```python
    snap = SignalSnapshot(
        ...
        market=payload.get("market", "crypto"),  # ← 新增
    )
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py -k "cn_symbol or cn_writes_market" -v
```
Expected: 2 passed

- [ ] **Step 6: 全量信号回归**

```bash
uv run python -m pytest tests/test_signal_cli.py -q
```
Expected: 全部通过（原有测试数 + 2）

- [ ] **Step 7: Commit**

```bash
git add src/hiveflow/application/signals.py src/hiveflow/application/signal_snapshots.py tests/test_signal_cli.py
git commit -m "feat: signal 系统加入 SIGNAL_PARAMS market-aware 分发，输出与落库加 market 字段"
```

---

## Chunk 6: CLI + Doctor + 全量回归

### Task 10: CLI 新命令与 `--market` 过滤

**Files:**
- Modify: `src/hiveflow/cli.py`
- Modify: `tests/test_cli.py`（追加测试）

#### 10a: `positions import-csv`

- [ ] **Step 1: 写失败测试（追加到 `tests/test_cli.py`）**

```python
# tests/test_cli.py — 在文件末尾追加
import json
from pathlib import Path
from typer.testing import CliRunner as TRunner
from hiveflow.cli import app as hiveflow_app


def test_positions_import_csv_valid(tmp_path: Path, monkeypatch) -> None:
    """positions import-csv 正常 A 股 CSV 导入成功，exit_code=0。"""
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    create_all_tables(Settings(database_url=db_url))

    csv_file = tmp_path / "cn.csv"
    csv_file.write_text(
        "symbol,quantity,avg_cost,market_value\n000001.SZ,1000,12.50,13200\n",
        encoding="utf-8",
    )

    result = TRunner().invoke(hiveflow_app, ["positions", "import-csv", "--file", str(csv_file)])
    assert result.exit_code == 0, result.stdout
    assert "1" in result.stdout


def test_positions_import_csv_crypto_symbol_rejected(tmp_path: Path, monkeypatch) -> None:
    """positions import-csv 拒绝加密 symbol，exit_code=1。"""
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    create_all_tables(Settings(database_url=db_url))

    csv_file = tmp_path / "bad.csv"
    csv_file.write_text(
        "symbol,quantity,avg_cost,market_value\nBTC,0.5,50000,25000\n", encoding="utf-8"
    )

    result = TRunner().invoke(hiveflow_app, ["positions", "import-csv", "--file", str(csv_file)])
    assert result.exit_code == 1


def test_market_data_sync_cn_json_output(tmp_path: Path, monkeypatch) -> None:
    """market-data sync --market cn 调用 cn_sync 并返回 JSON。"""
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables
    create_all_tables(Settings(database_url=db_url))

    from unittest.mock import MagicMock, patch
    from hiveflow.application.cn_sync import CNSyncResult

    mock_result = CNSyncResult(imported=3, symbols=["000001.SZ"], source="akshare")

    with patch("hiveflow.cli.sync_cn_market_data", return_value=mock_result):
        result = TRunner().invoke(
            hiveflow_app,
            ["market-data", "sync", "--market", "cn",
             "--symbols", "000001.SZ", "--output", "json"],
        )
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["imported"] == 3
    assert "000001.SZ" in payload["symbols"]


def test_summary_all_markets_json_schema(tmp_path: Path, monkeypatch) -> None:
    """`summary --market all --output json` 包含 markets.crypto 和 markets.cn_a_share，无 total_value。"""
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    with get_session(settings) as session:
        session.add(Position(symbol="BTC", quantity=1, market_value=50000, weight=0.7, market="crypto"))
        session.add(Position(symbol="000001.SZ", quantity=1000, market_value=13200, weight=1.0, market="cn_a_share"))
        session.commit()

    result = TRunner().invoke(hiveflow_app, ["summary", "--market", "all", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "markets" in payload
    assert "crypto" in payload["markets"]
    assert "cn_a_share" in payload["markets"]
    assert "total_value" not in payload  # 不做跨市场合算
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_cli.py -k "import_csv or sync_cn or all_markets" -v
```
Expected: 命令不存在（AttributeError / UsageError）

- [ ] **Step 3: 在 `cli.py` 添加 `positions import-csv` 命令**

在 `@positions_app.command("template")` 定义之后加：

```python
@positions_app.command("import-csv")
def import_cn_positions_command(
    file: Path = typer.Option(..., "--file", "-f", help="A 股持仓 CSV 文件路径"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从 CSV 导入 A 股持仓（symbol 格式如 000001.SZ）。"""
    from hiveflow.application.positions import import_cn_positions_from_csv, CNImportResult
    try:
        result = import_cn_positions_from_csv(str(file), settings=Settings())
    except (ValueError, FileNotFoundError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]导入成功：{result.imported} 条 A 股持仓[/green]")
        console.print(f"文件：{result.file}")
```

- [ ] **Step 4: 在 `cli.py` 添加 `market-data sync` 命令**

在 `cli.py` 顶部 import 处新增（在已有 application imports 旁）：

```python
from hiveflow.application.cn_sync import sync_cn_market_data
```

在 `@market_data_app.command("summary")` 之后加：

```python
@market_data_app.command("sync")
def sync_market_data_command(
    market: str = typer.Option(..., "--market", "-m", help="市场：cn"),
    symbols: str = typer.Option(..., "--symbols", "-s", help="逗号分隔的 symbol 列表，如 000001.SZ,600000.SH"),
    days: int = typer.Option(90, "--days", "-d", help="拉取最近 N 天数据"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """从第三方数据源拉取行情并落库（当前支持 --market cn）。"""
    if market != "cn":
        typer.echo(f"暂不支持市场：{market!r}，当前只支持 cn", err=True)
        raise typer.Exit(1)

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    try:
        result = sync_cn_market_data(symbol_list, days=days, settings=Settings())
    except ImportError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1)
    except Exception as exc:
        typer.echo(f"同步失败：{exc}", err=True)
        raise typer.Exit(1)

    if output == "json":
        typer.echo(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        console.print(f"[green]同步成功：{result.imported} 条行情记录[/green]")
        console.print(f"来源：{result.source}，symbols：{', '.join(result.symbols)}")
```

- [ ] **Step 5: 修改 `summary_command`，支持 `--market` 参数**

在 `summary_command` 函数签名加参数：

```python
@app.command("summary")
def summary_command(
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
    theme: str = typer.Option("hacker", "--theme", help="显示主题：hacker/minimal"),
    envelope: bool = typer.Option(False, "--envelope", help="JSON 输出使用统一 envelope"),
    json_schema: bool = typer.Option(False, "--json-schema", help="输出 JSON Schema"),
    market: str = typer.Option("crypto", "--market", "-m", help="市场过滤：crypto/cn/all"),
) -> None:
```

在函数体开头（现有逻辑之前）加 market 分支处理：

```python
    if market not in {"crypto", "cn", "all"}:
        typer.echo(f"不支持的 --market 值：{market!r}，支持 crypto / cn / all", err=True)
        raise typer.Exit(1)

    if market in {"all", "cn"}:
        from hiveflow.application.summary import get_market_summary
        ms = get_market_summary(settings=Settings())
        if market == "cn":
            # 只返回 A 股子视图
            ms = {"markets": {"cn_a_share": ms["markets"]["cn_a_share"]}, "note": ms["note"]}
        if output == "json":
            typer.echo(json.dumps(ms, ensure_ascii=False, indent=2))
        else:
            for mkt, info in ms["markets"].items():
                console.print(f"[bold]{mkt}[/bold]: {info}")
        return
    # market == "crypto"：原有逻辑不变
```

同时在 `test_cli.py` 追加 `--market cn` 测试：

```python
def test_summary_cn_market_json_schema(tmp_path: Path, monkeypatch) -> None:
    """`summary --market cn --output json` 只包含 cn_a_share，无 crypto。"""
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", db_url)

    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.positions import Position
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    with get_session(settings) as session:
        session.add(Position(symbol="000001.SZ", quantity=1000, market_value=13200, weight=1.0, market="cn_a_share"))
        session.commit()

    result = TRunner().invoke(hiveflow_app, ["summary", "--market", "cn", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "markets" in payload
    assert "cn_a_share" in payload["markets"]
    assert "crypto" not in payload["markets"]
```

- [ ] **Step 6: 在 `application/summary.py` 末尾添加 `get_market_summary`**

```python
def get_market_summary(settings=None) -> dict:
    """返回各市场持仓汇总（不做跨市场货币合算）。"""
    from hiveflow.domain.market import CRYPTO, CN_A_SHARE
    from hiveflow.domain.positions import Position
    from sqlmodel import select

    create_all_tables(settings)
    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()

    crypto_positions = [p for p in positions if getattr(p, "market", CRYPTO) == CRYPTO]
    cn_positions = [p for p in positions if getattr(p, "market", CRYPTO) == CN_A_SHARE]

    return {
        "markets": {
            CRYPTO: {
                "position_count": len(crypto_positions),
                "total_market_value_usdt": round(sum(p.market_value for p in crypto_positions), 2),
                "currency": "USDT",
            },
            CN_A_SHARE: {
                "position_count": len(cn_positions),
                "total_market_value_cny": round(sum(p.market_value for p in cn_positions), 2),
                "currency": "CNY",
            },
        },
        "note": "跨市场货币未合算，各市场独立展示",
    }
```

- [ ] **Step 7: 运行新 CLI 测试，确认通过**

```bash
uv run python -m pytest tests/test_cli.py -k "import_csv or sync_cn or all_markets" -v
```
Expected: 4 passed

- [ ] **Step 8: Commit**

```bash
git add src/hiveflow/cli.py src/hiveflow/application/summary.py tests/test_cli.py
git commit -m "feat: CLI 新增 positions import-csv / market-data sync --market cn / summary --market all"
```

---

### Task 11: Doctor 检查 A 股依赖

**Files:**
- Modify: `src/hiveflow/application/system.py`
- Modify: `tests/test_health_check.py`（追加测试）

- [ ] **Step 1: 追加测试到 `tests/test_health_check.py`**

```python
# tests/test_health_check.py — 在文件末尾追加

def test_doctor_includes_cn_dependency_check(tmp_path) -> None:
    """doctor 结果应包含 A 股依赖检查项。"""
    import os
    os.environ["HIVEFLOW_DATABASE_URL"] = f"sqlite:///{tmp_path / 'hiveflow.db'}"

    from hiveflow.application.system import run_doctor
    result = run_doctor()
    check_names = [c.name for c in result.checks]
    assert any("A 股" in name or "cn_market" in name or "akshare" in name.lower() for name in check_names)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_health_check.py -k "cn_dependency" -v
```
Expected: FAIL（无 A 股相关检查项）

- [ ] **Step 3: 在 `application/system.py` 的 `run_doctor` 函数中追加 A 股依赖检查**

找到 `run_doctor` 函数中构建 `checks` 列表的部分，在末尾追加：

```python
    # A 股数据依赖检查（settings 变量已在函数开头 settings = Settings() 定义）
    import importlib
    cn_source = getattr(settings, "cn_market_data_source", "akshare")
    try:
        importlib.import_module(cn_source)
        checks.append(DoctorCheckView(
            name=f"A 股数据依赖 ({cn_source})",
            status="ok",
            detail=f"{cn_source} 已安装，A 股行情同步可用。",
        ))
    except ImportError:
        checks.append(DoctorCheckView(
            name=f"A 股数据依赖 ({cn_source})",
            status="warn",
            detail=f"{cn_source} 未安装。如需 A 股功能，运行: uv pip install 'hiveflow[cn]'",
        ))
```

注意：`run_doctor` 函数开头已有 `settings = Settings()`（见现有代码第 84 行），直接使用 `settings` 变量，不要引入新变量名。

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_health_check.py -k "cn_dependency" -v
```
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/system.py tests/test_health_check.py
git commit -m "feat: doctor 新增 A 股依赖检查项"
```

---

### Task 12: 全量回归

**Files:** 无新增

- [ ] **Step 1: 运行完整测试套件**

```bash
uv run python -m pytest -q
```
Expected: 全部通过（基线 280+ passed + 本计划新增约 30 个测试，0 failed）

- [ ] **Step 2: 如有失败，定位并修复**

优先排查：
- `tests/test_cli.py`：summary/positions/market-data 命令的已有测试是否受 `--market` 新参数影响（typer 默认值应保证向后兼容）
- `tests/test_risk_engine.py`：compute_volatility 调用方是否需要更新
- `tests/test_signal_cli.py`：signal snapshot 是否在 market 字段上有断言冲突

- [ ] **Step 3: 最终 lint**

```bash
uv run ruff check .
```
Expected: 无错误（如有，逐一修复后再次运行）

- [ ] **Step 4: 最终 commit（如有修复）**

```bash
git add -A
git commit -m "fix: A 股 Phase 1 全量回归修复"
```

- [ ] **Step 5: 打印 git log，确认 commit 历史整洁**

```bash
git log --oneline -12
```

---

## 验收清单

在宣布 Phase 1 完成前，逐项确认：

- [ ] `uv run python -m pytest -q` 全部通过，0 failed
- [ ] `uv run ruff check .` 无错误
- [ ] `hiveflow positions import-csv --help` 显示 A 股导入命令帮助
- [ ] `hiveflow market-data sync --market cn --symbols 000001.SZ --days 30` 在 akshare 安装后可执行（或报清晰 ImportError）
- [ ] `hiveflow summary --market all --output json` 输出含 `markets.crypto` 和 `markets.cn_a_share`
- [ ] `hiveflow doctor` 输出包含 A 股依赖检查项
- [ ] 对现有加密路径无任何行为变更（OKX sync / positions list / trade execute 等全部向后兼容）
