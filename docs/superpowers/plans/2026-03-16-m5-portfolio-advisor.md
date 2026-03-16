# M5 Portfolio Advisor + 调仓执行闭环 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现网格持仓区分、回测从 DB 运行、目标配比来自回测、OKX 现货下单执行，以及两个 AI Skill 文件，打通"分析 → 报告 → 确认 → 执行"完整闭环。

**Architecture:** HiveFlow 承担数据层与执行层（CLI + SQLite），Skill 文件包含分析逻辑与投资框架提示词，Claude Agent 读 Skill 后编排整个流程。新增 `GridPosition` 表与 OKX 网格 API 对接，`BacktestResult` 添加 `weights_snapshot` 字段存储配比快照，新增 `trade execute` 命令对接 OKX Trade API。

**Tech Stack:** Python 3.12+, typer, SQLModel, SQLite, urllib.request（标准库）, pydantic-settings, rich, pytest

---

## 文件结构

**新建：**
- `src/hiveflow/domain/grid_positions.py` — GridPosition SQLModel 表
- `src/hiveflow/application/trade.py` — trade execute 用例
- `tests/test_okx_grid_provider.py`
- `tests/test_sync_grid.py`
- `tests/test_positions_list_grid.py`
- `tests/test_backtest_from_db.py`
- `tests/test_targets_from_backtest.py`
- `tests/test_trade_execute.py`
- `~/.agents/skills/hiveflow-daily-check/SKILL.md`
- `~/.agents/skills/hiveflow-portfolio-advisor/SKILL.md`

**修改：**
- `src/hiveflow/domain/backtests.py` — 新增 `weights_snapshot` 字段
- `src/hiveflow/infrastructure/okx/okx_provider.py` — 新增 `fetch_grid_positions()` / `place_market_order()`
- `src/hiveflow/application/sync.py` — 新增网格持仓同步
- `src/hiveflow/application/positions.py` — `list_positions()` 返回自由+网格两组
- `src/hiveflow/application/backtest.py` — 支持从 DB 读行情，`BacktestResultView` 加 `id`
- `src/hiveflow/services/backtest_engine.py` — 新增 `load_close_prices_from_db()`
- `src/hiveflow/config.py` — 新增 3 个 Trade API 字段
- `src/hiveflow/db.py` — `_run_lightweight_migrations` 加 `weights_snapshot` 列迁移
- `src/hiveflow/cli.py` — 修改 `positions list`、`backtest run`；新增 `targets set-from-backtest`、`trade` 命令组

---

## Chunk 1: 网格持仓

### Task 1: GridPosition 模型 + OkxProvider.fetch_grid_positions()

**Files:**
- Create: `src/hiveflow/domain/grid_positions.py`
- Modify: `src/hiveflow/infrastructure/okx/okx_provider.py`
- Test: `tests/test_okx_grid_provider.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_okx_grid_provider.py
import json
from unittest.mock import MagicMock, patch
import pytest
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxGridPosition


def _resp(body: dict) -> MagicMock:
    r = MagicMock()
    r.status = 200
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


def test_fetch_grid_positions_returns_spot_grids() -> None:
    payload = {
        "code": "0",
        "data": [
            {
                "algoId": "001",
                "instId": "BTC-USDT",
                "instType": "SPOT",
                "baseSz": "0.005",
                "quoteSz": "100",
                "state": "running",
            },
            {
                "algoId": "002",
                "instId": "ETH-USDT",
                "instType": "SPOT",
                "baseSz": "0.1",
                "quoteSz": "50",
                "state": "running",
            },
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()
    assert len(positions) == 2
    assert positions[0].symbol == "BTC"
    assert positions[0].grid_id == "001"
    assert positions[0].inst_id == "BTC-USDT"
    assert positions[0].base_quantity == 0.005
    assert positions[0].quote_quantity == 100.0
    assert positions[0].state == "running"


def test_fetch_grid_positions_returns_empty_when_none() -> None:
    payload = {"code": "0", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        positions = OkxProvider("k", "s", "p").fetch_grid_positions()
    assert positions == []
```

- [ ] **Step 2: 运行确认失败** `uv run python -m pytest tests/test_okx_grid_provider.py -v`

- [ ] **Step 3: 创建 GridPosition 模型**

```python
# src/hiveflow/domain/grid_positions.py
"""OKX 网格机器人持仓模型。"""
from datetime import datetime
from sqlmodel import Field, SQLModel
from hiveflow.domain.common import utc_now


class GridPosition(SQLModel, table=True):
    """网格机器人持有的资产（不参与再平衡计算）。"""
    id: int | None = Field(default=None, primary_key=True)
    symbol: str           # 资产名（BTC）
    grid_id: str          # 网格机器人 ID
    inst_id: str          # 交易对（BTC-USDT）
    base_quantity: float  # 持有基础资产数量
    quote_quantity: float # 持有报价资产（USDT）数量
    state: str            # running / stopped
    synced_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 4: 在 okx_provider.py 新增 OkxGridPosition dataclass 和 fetch_grid_positions()**

在 `OkxCandle` 定义之后新增：

```python
@dataclass(frozen=True)
class OkxGridPosition:
    symbol: str
    grid_id: str
    inst_id: str
    base_quantity: float
    quote_quantity: float
    state: str
```

在 `OkxProvider` 类中新增方法：

```python
def fetch_grid_positions(self) -> list[OkxGridPosition]:
    """拉取现货网格机器人持仓（GET /api/v5/tradingBot/grid/positions?instType=SPOT）。"""
    try:
        data = self._get_auth("/api/v5/tradingBot/grid/positions?instType=SPOT")
    except Exception:
        # 网格接口可能因权限不足返回错误，静默返回空列表
        return []
    result = []
    for item in data:
        if item.get("instType") != "SPOT":
            continue
        inst_id = item.get("instId", "")
        symbol = inst_id.split("-")[0].upper()
        result.append(OkxGridPosition(
            symbol=symbol,
            grid_id=str(item.get("algoId", "")),
            inst_id=inst_id,
            base_quantity=float(item.get("baseSz") or 0),
            quote_quantity=float(item.get("quoteSz") or 0),
            state=str(item.get("state", "unknown")),
        ))
    return result
```

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_okx_grid_provider.py -v` — 期望 2 passed
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q` — 期望全部通过
- [ ] **Step 7: 提交** `git commit -m "feat: 新增 OkxGridPosition 和 fetch_grid_positions()"`

---

### Task 2: sync 同步网格持仓

**Files:**
- Modify: `src/hiveflow/application/sync.py`
- Modify: `src/hiveflow/db.py` — 确保 GridPosition 表被创建
- Test: `tests/test_sync_grid.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sync_grid.py
from unittest.mock import MagicMock
from sqlmodel import select
from hiveflow.application.sync import sync_from_okx
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.grid_positions import GridPosition
from hiveflow.infrastructure.okx.okx_provider import OkxGridPosition, OkxPosition


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/sg.db",
        okx_api_key="k", okx_api_secret="s", okx_api_passphrase="p",
    )


def _provider(positions=None, grid_positions=None) -> MagicMock:
    p = MagicMock()
    p.fetch_positions.return_value = positions or []
    p.fetch_tickers.return_value = []
    p.fetch_candles.return_value = []
    p.fetch_grid_positions.return_value = grid_positions or []
    return p


def test_sync_writes_grid_positions(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    grids = [OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                              base_quantity=0.005, quote_quantity=100.0, state="running")]
    sync_from_okx(provider=_provider(grid_positions=grids), settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(GridPosition)).all()
    assert len(rows) == 1
    assert rows[0].symbol == "BTC"
    assert rows[0].grid_id == "001"


def test_sync_clears_grid_positions_on_each_run(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    g1 = OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                          base_quantity=0.005, quote_quantity=100.0, state="running")
    sync_from_okx(provider=_provider(grid_positions=[g1]), settings=settings)
    sync_from_okx(provider=_provider(grid_positions=[]), settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(GridPosition)).all()
    assert len(rows) == 0


def test_sync_result_includes_grid_count(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    grids = [
        OkxGridPosition(symbol="BTC", grid_id="001", inst_id="BTC-USDT",
                        base_quantity=0.005, quote_quantity=100.0, state="running"),
        OkxGridPosition(symbol="ETH", grid_id="002", inst_id="ETH-USDT",
                        base_quantity=0.1, quote_quantity=50.0, state="running"),
    ]
    result = sync_from_okx(provider=_provider(grid_positions=grids), settings=settings)
    assert result.grids_synced == 2
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 在 sync.py 的 SyncResult 中新增 grids_synced 字段**

```python
@dataclass(frozen=True)
class SyncResult:
    synced_at: datetime
    positions_synced: int
    prices_synced: int
    candles_synced: int
    grids_synced: int          # 新增
    total_value_usdt: float

    def to_dict(self) -> dict:
        return {
            "synced_at": self.synced_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "positions_synced": self.positions_synced,
            "prices_synced": self.prices_synced,
            "candles_synced": self.candles_synced,
            "grids_synced": self.grids_synced,          # 新增
            "total_value_usdt": round(self.total_value_usdt, 2),
        }
```

- [ ] **Step 4: 在 sync_from_okx() 中新增网格同步逻辑**

在 `okx_positions = provider.fetch_positions()` 之后新增：

```python
okx_grids = provider.fetch_grid_positions()
```

在事务写入块（`with get_session(...) as session:`）中，在 `session.commit()` 之前新增：

```python
# 网格持仓：全量替换
from hiveflow.domain.grid_positions import GridPosition
session.exec(delete(GridPosition))
for g in okx_grids:
    session.add(GridPosition(
        symbol=g.symbol, grid_id=g.grid_id, inst_id=g.inst_id,
        base_quantity=g.base_quantity, quote_quantity=g.quote_quantity,
        state=g.state,
    ))
```

修改 return 语句加入 `grids_synced=len(okx_grids)`。

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_sync_grid.py -v` — 期望 3 passed
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 7: 提交** `git commit -m "feat: sync 新增网格持仓同步"`

---

### Task 3: positions list 显示网格区块

**Files:**
- Modify: `src/hiveflow/application/positions.py`
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_positions_list_grid.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_positions_list_grid.py
from typer.testing import CliRunner
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.grid_positions import GridPosition
from hiveflow.domain.positions import Position
import json


def _setup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/p.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        s.add(Position(symbol="BTC", quantity=0.001, market_value=700.0, weight=0.7))
        s.add(GridPosition(symbol="ETH", grid_id="001", inst_id="ETH-USDT",
                           base_quantity=0.1, quote_quantity=50.0, state="running"))
        s.commit()
    return settings


def test_positions_list_shows_grid_section(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list"])
    assert result.exit_code == 0
    assert "自由持仓" in result.output
    assert "网格持仓" in result.output
    assert "ETH" in result.output


def test_positions_list_json_includes_grid(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "free" in data
    assert "grid" in data
    assert data["grid"][0]["symbol"] == "ETH"


def test_positions_list_no_grid_section_when_empty(monkeypatch, tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/p2.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        s.add(Position(symbol="BTC", quantity=0.001, market_value=700.0, weight=1.0))
        s.commit()
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["positions", "list"])
    assert result.exit_code == 0
    assert "网格持仓" not in result.output
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 在 positions.py 中新增 GridPositionView 和 list_grid_positions()**

在文件**顶部 import 区域**添加以下两行（不要放在文件末尾），确保 `select` 和 `GridPosition` 在模块加载时可用：

```python
from sqlmodel import select  # 若已存在则跳过
from hiveflow.domain.grid_positions import GridPosition


@dataclass(frozen=True)
class GridPositionView:
    symbol: str
    grid_id: str
    inst_id: str
    base_quantity: float
    quote_quantity: float
    state: str

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "grid_id": self.grid_id,
            "inst_id": self.inst_id,
            "base_quantity": round(self.base_quantity, 6),
            "quote_quantity": round(self.quote_quantity, 2),
            "state": self.state,
        }


def list_grid_positions(settings: Settings | None = None) -> list[GridPositionView]:
    """返回当前所有网格持仓。"""
    create_all_tables(settings)
    with get_session(settings) as session:
        rows = session.exec(select(GridPosition)).all()
    return [
        GridPositionView(
            symbol=r.symbol, grid_id=r.grid_id, inst_id=r.inst_id,
            base_quantity=r.base_quantity, quote_quantity=r.quote_quantity,
            state=r.state,
        )
        for r in rows
    ]
```

- [ ] **Step 4: 修改 cli.py 的 list_positions_command**

找到 `@positions_app.command("list")` 函数，在文件顶部 import 处新增：

```python
from hiveflow.application.positions import list_grid_positions, GridPositionView
```

修改 `list_positions_command` 函数体，在获取 `positions` 之后新增：

```python
grid_positions = list_grid_positions()
```

在 `output == "json"` 分支替换原来的 payload：

```python
if output_format == "json":
    payload = {
        "free": [p.to_dict() for p in positions],
        "grid": [g.to_dict() for g in grid_positions],
    }
    _print_json(payload=payload, command="positions.list", envelope=envelope)
    return
```

在 pretty 输出末尾追加网格区块（仅有网格持仓时显示）：

```python
if grid_positions:
    console.print()
    console.print("[bold]:: 网格持仓（不参与调仓计算）::[/bold]")
    grid_table = Table(box=box.SIMPLE, show_header=True)
    grid_table.add_column("标的", style="bold")
    grid_table.add_column("基础资产")
    grid_table.add_column("USDT")
    grid_table.add_column("网格 ID")
    grid_table.add_column("交易对")
    grid_table.add_column("状态")
    for g in grid_positions:
        state_color = "green" if g.state == "running" else "yellow"
        grid_table.add_row(
            g.symbol, str(g.base_quantity), str(g.quote_quantity),
            g.grid_id, g.inst_id, f"[{state_color}]{g.state}[/{state_color}]",
        )
    console.print(grid_table)
```

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_positions_list_grid.py -v` — 期望 3 passed
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 7: 提交** `git commit -m "feat: positions list 区分自由持仓与网格持仓"`

---

## Chunk 2: Backtest 从 DB 运行

### Task 4: BacktestResult 模型新增 weights_snapshot + DB 迁移

**Files:**
- Modify: `src/hiveflow/domain/backtests.py`
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_backtest_from_db.py`（仅验证迁移，完整测试在 Task 5）

- [ ] **Step 1: 修改 backtests.py**

```python
# src/hiveflow/domain/backtests.py
"""回测结果模型。"""
from datetime import datetime
from sqlmodel import Field, SQLModel
from hiveflow.domain.common import utc_now


class BacktestResult(SQLModel, table=True):
    """策略回测结果记录。"""
    id: int | None = Field(default=None, primary_key=True)
    strategy_name: str
    prices_file: str          # CSV 路径或哨兵值 "DB:MarketBar"
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None = Field(default=None)  # JSON: {"BTC":0.4,"ETH":0.3,...}
    created_at: datetime = Field(default_factory=utc_now)
```

- [ ] **Step 2: 在 db.py 的 _run_lightweight_migrations 中添加列迁移**

⚠️ 重要：`weights_snapshot` 迁移必须独立于 `strategy` 表的存在检查，避免在没有 `strategy` 表的 DB（如 M4 用户）上被跳过。

将 `_run_lightweight_migrations` 重构为每张表独立处理：

```python
def _run_lightweight_migrations(engine) -> None:
    """执行轻量迁移，确保旧库可兼容新增字段。"""
    if not engine.url.drivername.startswith("sqlite"):
        return

    with engine.begin() as conn:
        tables = {row[0] for row in conn.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}

        # strategy 表：dimension 列
        if "strategy" in tables:
            columns = conn.exec_driver_sql("PRAGMA table_info('strategy')").fetchall()
            column_names = {row[1] for row in columns}
            if "dimension" not in column_names:
                conn.exec_driver_sql("ALTER TABLE strategy ADD COLUMN dimension VARCHAR")

        # backtestresult 表：weights_snapshot 列（独立于 strategy 表检查）
        if "backtestresult" in tables:
            bt_cols = conn.exec_driver_sql("PRAGMA table_info('backtestresult')").fetchall()
            bt_col_names = {row[1] for row in bt_cols}
            if "weights_snapshot" not in bt_col_names:
                conn.exec_driver_sql(
                    "ALTER TABLE backtestresult ADD COLUMN weights_snapshot TEXT"
                )
```

- [ ] **Step 3: 验证迁移可以在现有 DB 上正常运行**

```bash
uv run python -c "from hiveflow.db import create_all_tables; create_all_tables(); print('OK')"
```

期望输出 `OK` 无报错。

- [ ] **Step 4: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 5: 提交** `git commit -m "feat: BacktestResult 新增 weights_snapshot 字段"`

---

### Task 5: backtest_engine 支持从 DB 读取 + application 层更新

**Files:**
- Modify: `src/hiveflow/services/backtest_engine.py`
- Modify: `src/hiveflow/application/backtest.py`
- Test: `tests/test_backtest_from_db.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_backtest_from_db.py
import json
from datetime import datetime, timezone
from typer.testing import CliRunner
from sqlmodel import select
from hiveflow.application.backtest import run_backtest_for_strategy
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.market_data import MarketBar


def _setup(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/bt.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        # 目标配比
        s.add(TargetAllocation(strategy_name="test_strat", symbol="BTC", target_weight=0.6))
        s.add(TargetAllocation(strategy_name="test_strat", symbol="ETH", target_weight=0.4))
        # 行情数据（7 天）
        for i in range(7):
            ts = datetime(2026, 3, i + 1, tzinfo=timezone.utc)
            s.add(MarketBar(symbol="BTC", timestamp=ts,
                            open=70000.0, high=71000.0, low=69000.0,
                            close=70000.0 + i * 100, volume=100.0))
            s.add(MarketBar(symbol="ETH", timestamp=ts,
                            open=3000.0, high=3100.0, low=2900.0,
                            close=3000.0 + i * 10, volume=500.0))
        s.commit()
    return settings


def test_backtest_run_from_db(tmp_path) -> None:
    settings = _setup(tmp_path)
    result = run_backtest_for_strategy(
        strategy_name="test_strat",
        prices_file=None,
        settings=settings,
    )
    assert result.periods > 0
    assert result.prices_file == "DB:MarketBar"
    assert result.weights_snapshot is not None
    snapshot = json.loads(result.weights_snapshot)
    assert snapshot["BTC"] == 0.6
    assert snapshot["ETH"] == 0.4


def test_backtest_run_stores_weights_snapshot(tmp_path) -> None:
    settings = _setup(tmp_path)
    run_backtest_for_strategy(strategy_name="test_strat", prices_file=None, settings=settings)
    with get_session(settings) as s:
        row = s.exec(select(BacktestResult)).first()
    assert row is not None
    assert row.weights_snapshot is not None
    assert json.loads(row.weights_snapshot)["BTC"] == 0.6


def test_backtest_run_db_cli(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["backtest", "run", "--strategy", "test_strat"])
    assert result.exit_code == 0
    assert "回测完成" in result.output


def test_backtest_list_includes_id(monkeypatch, tmp_path) -> None:
    settings = _setup(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    CliRunner().invoke(app, ["backtest", "run", "--strategy", "test_strat"])
    result = CliRunner().invoke(app, ["backtest", "list", "--output", "json"])
    data = json.loads(result.output)
    assert len(data) >= 1
    assert "id" in data[0]
    assert data[0]["id"] is not None
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 在 backtest_engine.py 末尾新增 load_close_prices_from_db()**

```python
def load_close_prices_from_db(
    symbols: list[str],
    settings=None,
) -> dict[str, list[PriceBar]]:
    """从 DB 的 MarketBar 表读取 close 序列。"""
    from sqlmodel import select
    from hiveflow.db import create_all_tables, get_session
    from hiveflow.domain.market_data import MarketBar

    create_all_tables(settings)
    result: dict[str, list[PriceBar]] = {}
    with get_session(settings) as session:
        for symbol in symbols:
            rows = session.exec(
                select(MarketBar)
                .where(MarketBar.symbol == symbol)
                .order_by(MarketBar.timestamp)
            ).all()
            if not rows:
                continue
            result[symbol] = [
                PriceBar(
                    symbol=r.symbol,
                    timestamp=r.timestamp.isoformat(),
                    close=r.close,
                )
                for r in rows
            ]
    return result
```

- [ ] **Step 4: 修改 backtest.py 中的 BacktestResultView 和 run_backtest_for_strategy()**

`BacktestResultView` 新增 `id` 和 `weights_snapshot` 字段：

```python
@dataclass(frozen=True)
class BacktestResultView:
    id: int | None
    strategy_name: str
    prices_file: str
    periods: int
    total_return: float
    max_drawdown: float
    sharpe: float
    weights_snapshot: str | None
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "strategy_name": self.strategy_name,
            "prices_file": self.prices_file,
            "periods": self.periods,
            "total_return": round(self.total_return, 6),
            "max_drawdown": round(self.max_drawdown, 6),
            "sharpe": round(self.sharpe, 6),
            "weights_snapshot": self.weights_snapshot,
            "created_at": self.created_at,
        }
```

修改 `run_backtest_for_strategy` 签名，`prices_file` 变为可选，新增 `settings` 参数：

```python
def run_backtest_for_strategy(
    strategy_name: str,
    prices_file: Path | None = None,
    fee_bps: float = 0.0,
    slippage_bps: float = 0.0,
    settings=None,
) -> BacktestResultView:
    """执行单策略回测并持久化结果。prices_file=None 时从 DB 读取行情。"""
    from hiveflow.services.backtest_engine import load_close_prices_from_db
    import json as _json

    weights = _load_target_weights(strategy_name=strategy_name, settings=settings)

    if prices_file is not None:
        prices = load_close_prices(file=prices_file)
        source = str(prices_file)
    else:
        prices = load_close_prices_from_db(symbols=list(weights.keys()), settings=settings)
        source = "DB:MarketBar"

    metrics = run_weighted_backtest(
        prices=prices, weights=weights, fee_bps=fee_bps, slippage_bps=slippage_bps,
    )
    weights_json = _json.dumps({k: v for k, v in weights.items()})

    create_all_tables(settings)
    with get_session(settings) as session:
        row = BacktestResult(
            strategy_name=strategy_name,
            prices_file=source,
            periods=metrics.periods,
            total_return=metrics.total_return,
            max_drawdown=metrics.max_drawdown,
            sharpe=metrics.sharpe,
            weights_snapshot=weights_json,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return _to_view(row)
```

新增辅助函数 `_to_view(row)` 避免重复：

```python
def _to_view(row: BacktestResult) -> BacktestResultView:
    return BacktestResultView(
        id=row.id,
        strategy_name=row.strategy_name,
        prices_file=row.prices_file,
        periods=row.periods,
        total_return=row.total_return,
        max_drawdown=row.max_drawdown,
        sharpe=row.sharpe,
        weights_snapshot=row.weights_snapshot,
        created_at=row.created_at.isoformat(),
    )
```

同步修改 `_load_target_weights` 接受 `settings` 参数，`list_backtest_results` 使用 `_to_view`。

- [ ] **Step 5: 修改 cli.py 的 run_backtest_command，--file 变为可选**

```python
@backtest_app.command("run")
def run_backtest_command(
    strategy: str = typer.Option(..., "--strategy", "-s", help="策略名称"),
    file: Path | None = typer.Option(None, "--file", "-f", help="行情 CSV（不填则从 DB 读）"),
    fee_bps: float = typer.Option(0.0, "--fee-bps", help="交易费率（基点）"),
    slippage_bps: float = typer.Option(0.0, "--slippage-bps", help="滑点（基点）"),
    output: str = typer.Option("pretty", "--output", "-o", help="输出格式：pretty/json"),
) -> None:
    """运行一次策略回测。不指定 --file 时从本地 DB 行情数据运行。"""
    output_format = _validate_output_format(output)
    try:
        result = run_backtest_for_strategy(
            strategy_name=strategy,
            prices_file=file,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
            settings=Settings(),
        )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    # ... 其余输出逻辑不变
```

- [ ] **Step 6: 运行测试** `uv run python -m pytest tests/test_backtest_from_db.py -v` — 期望 4 passed
- [ ] **Step 7: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 8: 提交** `git commit -m "feat: backtest run 支持从 DB 读取行情（--file 变为可选）"`

---

## Chunk 3: targets set-from-backtest

### Task 6: targets set-from-backtest 命令

**Files:**
- Modify: `src/hiveflow/application/backtest.py` — 新增 `set_targets_from_backtest()`
- Modify: `src/hiveflow/cli.py` — 新增 `targets set-from-backtest` 命令
- Test: `tests/test_targets_from_backtest.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_targets_from_backtest.py
import json
from datetime import datetime, timezone
from typer.testing import CliRunner
from sqlmodel import select
from hiveflow.application.backtest import set_targets_from_backtest
from hiveflow.cli import app
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.allocations import TargetAllocation
from hiveflow.domain.backtests import BacktestResult
from hiveflow.domain.market_data import MarketBar


def _setup_with_backtest(tmp_path):
    settings = Settings(database_url=f"sqlite:///{tmp_path}/t.db")
    create_all_tables(settings)
    snapshot = json.dumps({"BTC": 0.4, "ETH": 0.3, "USDT": 0.3})
    with get_session(settings) as s:
        row = BacktestResult(
            strategy_name="均衡版",
            prices_file="DB:MarketBar",
            periods=30,
            total_return=0.15,
            max_drawdown=-0.12,
            sharpe=1.2,
            weights_snapshot=snapshot,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        return settings, row.id


def test_set_targets_writes_allocations(tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    set_targets_from_backtest(backtest_id=bt_id, settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "均衡版"
        )).all()
    weights = {r.symbol: r.target_weight for r in rows}
    assert abs(weights["BTC"] - 0.4) < 0.001
    assert abs(weights["ETH"] - 0.3) < 0.001
    assert abs(weights["USDT"] - 0.3) < 0.001


def test_set_targets_replaces_existing(tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    with get_session(settings) as s:
        s.add(TargetAllocation(strategy_name="均衡版", symbol="SOL", target_weight=0.5))
        s.commit()
    set_targets_from_backtest(backtest_id=bt_id, settings=settings)
    with get_session(settings) as s:
        rows = s.exec(select(TargetAllocation).where(
            TargetAllocation.strategy_name == "均衡版"
        )).all()
    symbols = {r.symbol for r in rows}
    assert "SOL" not in symbols  # 旧记录应被清除


def test_set_targets_cli(monkeypatch, tmp_path) -> None:
    settings, bt_id = _setup_with_backtest(tmp_path)
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", settings.database_url)
    result = CliRunner().invoke(app, ["targets", "set-from-backtest", str(bt_id)])
    assert result.exit_code == 0
    assert "BTC" in result.output
    assert "40" in result.output


def test_set_targets_fails_on_missing_snapshot(tmp_path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path}/t2.db")
    create_all_tables(settings)
    with get_session(settings) as s:
        row = BacktestResult(
            strategy_name="test", prices_file="f.csv",
            periods=10, total_return=0.1, max_drawdown=-0.05, sharpe=1.0,
            weights_snapshot=None,
        )
        s.add(row)
        s.commit()
        s.refresh(row)
        bt_id = row.id
    with pytest.raises(ValueError, match="weights_snapshot"):
        set_targets_from_backtest(backtest_id=bt_id, settings=settings)
```

需要在文件顶部加 `import pytest`。

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 在 backtest.py 新增 set_targets_from_backtest()**

在 `backtest.py` 顶部 import 区域确保有：`from sqlmodel import delete, select`（与现有代码对齐）。

```python
def set_targets_from_backtest(backtest_id: int, settings=None) -> dict[str, float]:
    """从回测结果的 weights_snapshot 设置目标配比。返回写入的配比字典。"""
    import json as _json

    create_all_tables(settings)
    with get_session(settings) as session:
        row = session.get(BacktestResult, backtest_id)
        if row is None:
            raise ValueError(f"回测记录 #{backtest_id} 不存在。")
        if not row.weights_snapshot:
            raise ValueError(f"回测记录 #{backtest_id} 无 weights_snapshot，无法设置目标配比。")
        weights = _json.loads(row.weights_snapshot)
        strategy_name = row.strategy_name

        session.exec(delete(TargetAllocation).where(
            TargetAllocation.strategy_name == strategy_name
        ))
        for symbol, weight in weights.items():
            session.add(TargetAllocation(
                strategy_name=strategy_name,
                symbol=symbol,
                target_weight=weight,
            ))
        session.commit()
    return weights
```

- [ ] **Step 4: 在 cli.py 新增 targets set-from-backtest 命令**

在 `targets_app` 下新增（在现有命令之后）：

```python
@targets_app.command("set-from-backtest")
def targets_set_from_backtest_command(
    backtest_id: int = typer.Argument(..., help="回测记录 ID（来自 backtest list）"),
) -> None:
    """将回测结果的配比设为当前目标配比。"""
    from hiveflow.application.backtest import set_targets_from_backtest
    try:
        weights = set_targets_from_backtest(backtest_id=backtest_id)
    except ValueError as e:
        console.print(f"[bold red]错误：{e}[/bold red]")
        raise typer.Exit(code=1)
    console.print(f"[bold green]已设置目标配比（来自回测 #{backtest_id}）：[/bold green]")
    for symbol, weight in sorted(weights.items()):
        console.print(f"  {symbol}  {weight:.0%}")
```

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_targets_from_backtest.py -v` — 期望 4 passed
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 7: 提交** `git commit -m "feat: 新增 targets set-from-backtest 命令"`

---

## Chunk 4: trade execute

### Task 7: OKX Trade API + Settings 扩展

**Files:**
- Modify: `src/hiveflow/config.py`
- Modify: `src/hiveflow/infrastructure/okx/okx_provider.py`
- Test: `tests/test_trade_execute.py`（部分）

- [ ] **Step 1: 写失败测试（仅 provider 部分）**

```python
# tests/test_trade_execute.py
import json
from unittest.mock import MagicMock, patch
import pytest
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxOrderResult


def _resp(body: dict) -> MagicMock:
    r = MagicMock()
    r.status = 200
    r.read.return_value = json.dumps(body).encode()
    r.__enter__ = lambda s: s
    r.__exit__ = MagicMock(return_value=False)
    return r


def test_place_market_buy_order() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "123456", "clOrdId": "", "sCode": "0", "sMsg": ""}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        provider = OkxProvider("k", "s", "p")
        result = provider.place_market_order(inst_id="BTC-USDT", side="buy", usdt_amount=500.0)
    assert result.order_id == "123456"
    assert result.success is True


def test_place_market_sell_order() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "654321", "clOrdId": "", "sCode": "0", "sMsg": ""}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        provider = OkxProvider("k", "s", "p")
        result = provider.place_market_order(
            inst_id="ETH-USDT", side="sell", usdt_amount=200.0, current_price=3000.0
        )
    assert result.order_id == "654321"
    assert result.success is True


def test_place_order_returns_failure_on_error_code() -> None:
    payload = {
        "code": "0",
        "data": [{"ordId": "", "clOrdId": "", "sCode": "51008", "sMsg": "Insufficient balance"}],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as m:
        m.return_value = _resp(payload)
        result = OkxProvider("k", "s", "p").place_market_order(
            inst_id="BTC-USDT", side="buy", usdt_amount=500.0
        )
    assert result.success is False
    assert "Insufficient" in result.error_msg
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 在 config.py 新增 Trade API 字段**

```python
# OKX Trade API（下单专用，需 Trade 权限）
okx_trade_api_key: str | None = None
okx_trade_api_secret: str | None = None
okx_trade_passphrase: str | None = None
```

- [ ] **Step 4: 在 okx_provider.py 新增 OkxOrderResult dataclass 和 place_market_order()**

在 `OkxGridPosition` 定义之后新增：

```python
@dataclass(frozen=True)
class OkxOrderResult:
    order_id: str
    success: bool
    error_msg: str = ""
```

在 `OkxProvider` 类中新增方法：

```python
def place_market_order(
    self,
    inst_id: str,
    side: str,
    usdt_amount: float,
    current_price: float | None = None,
) -> OkxOrderResult:
    """下现货市价单。
    side='buy': sz 以 USDT 计（tgtCcy=quote_ccy）。
    side='sell': sz 以基础资产计，需传入 current_price 换算。
    """
    if side == "buy":
        sz = str(round(usdt_amount, 2))
        body: dict = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": "buy",
            "ordType": "market",
            "sz": sz,
            "tgtCcy": "quote_ccy",
        }
    else:
        if current_price is None or current_price <= 0:
            return OkxOrderResult(order_id="", success=False,
                                  error_msg="卖单需要提供 current_price")
        base_sz = round(usdt_amount / current_price, 8)
        body = {
            "instId": inst_id,
            "tdMode": "cash",
            "side": "sell",
            "ordType": "market",
            "sz": str(base_sz),
        }
    data = self._post_auth("/api/v5/trade/order", body)
    if not data:
        return OkxOrderResult(order_id="", success=False, error_msg="空响应")
    item = data[0]
    s_code = str(item.get("sCode", "0"))
    if s_code != "0":
        return OkxOrderResult(order_id="", success=False,
                               error_msg=item.get("sMsg", "未知错误"))
    return OkxOrderResult(order_id=str(item.get("ordId", "")), success=True)
```

同时新增 `_post_auth` 方法（统一使用模块级 `json`，不再引入局部 `_json`）：

```python
def _post_auth(self, path: str, body: dict) -> list:
    ts = datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    body_str = json.dumps(body)
    sign = self._sign("POST", path, ts, body_str)
    headers = {
        "OK-ACCESS-KEY": self._key,
        "OK-ACCESS-SIGN": sign,
        "OK-ACCESS-TIMESTAMP": ts,
        "OK-ACCESS-PASSPHRASE": self._pass,
    }
    req = urllib.request.Request(
        BASE_URL + path,
        data=body_str.encode(),
        headers={
            **headers,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            resp_body = json.loads(resp.read())
    except (TimeoutError, urllib.error.URLError) as e:
        if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
            raise OkxTimeoutError("网络超时，请稍后重试。")
        raise OkxTimeoutError(f"网络请求失败：{e}")
    except Exception as e:
        msg = str(e)
        if "401" in msg:
            raise OkxAuthError("OKX Trade API 鉴权失败（401）。")
        raise OkxTimeoutError(f"网络请求失败：{msg}")
    code = resp_body.get("code", "0")
    if code != "0":
        raise OkxAuthError(f"OKX API 错误 code={code}：{resp_body.get('msg')}")
    return resp_body.get("data", [])
```

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_trade_execute.py::test_place_market_buy_order tests/test_trade_execute.py::test_place_market_sell_order tests/test_trade_execute.py::test_place_order_returns_failure_on_error_code -v` — 期望 3 passed
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 7: 提交** `git commit -m "feat: OkxProvider 新增 place_market_order + Settings 新增 Trade API 字段"`

---

### Task 8: trade execute 用例 + CLI 命令

**Files:**
- Create: `src/hiveflow/application/trade.py`
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_trade_execute.py`（追加）

- [ ] **Step 1: 在 tests/test_trade_execute.py 末尾追加用例测试**

```python
# 追加到 tests/test_trade_execute.py

import json as _json
from typer.testing import CliRunner
from unittest.mock import patch
from hiveflow.application.trade import TradeOrder, execute_trades
from hiveflow.config import Settings
from hiveflow.infrastructure.okx.okx_provider import OkxOrderResult


def _trade_settings(monkeypatch):
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_API_KEY", "tk")
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_API_SECRET", "ts")
    monkeypatch.setenv("HIVEFLOW_OKX_TRADE_PASSPHRASE", "tp")


def test_execute_trades_all_success() -> None:
    orders = [
        TradeOrder(symbol="BTC", action="buy", usdt=500.0),
        TradeOrder(symbol="ETH", action="sell", usdt=200.0),
    ]
    mock_result = OkxOrderResult(order_id="123", success=True)
    with patch("hiveflow.application.trade.OkxProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.place_market_order.return_value = mock_result
        instance.fetch_tickers.return_value = []
        results = execute_trades(
            orders=orders,
            api_key="k", api_secret="s", passphrase="p",
        )
    assert all(r.success for r in results)


def test_execute_trades_partial_failure() -> None:
    orders = [
        TradeOrder(symbol="BTC", action="buy", usdt=500.0),
        TradeOrder(symbol="ETH", action="buy", usdt=200.0),
    ]
    def mock_order(inst_id, side, usdt_amount, current_price=None):
        if "BTC" in inst_id:
            return OkxOrderResult(order_id="123", success=True)
        return OkxOrderResult(order_id="", success=False, error_msg="余额不足")

    with patch("hiveflow.application.trade.OkxProvider") as MockProvider:
        instance = MockProvider.return_value
        instance.place_market_order.side_effect = mock_order
        instance.fetch_tickers.return_value = []
        results = execute_trades(
            orders=orders, api_key="k", api_secret="s", passphrase="p",
        )
    assert results[0].success is True
    assert results[1].success is False


def test_trade_execute_cli_no_trade_key() -> None:
    result = CliRunner().invoke(app, [
        "trade", "execute",
        "--orders", '[{"symbol":"BTC","action":"buy","usdt":100}]',
    ])
    assert result.exit_code == 1
    assert "TRADE" in result.output


def test_trade_execute_cli_success(monkeypatch) -> None:
    _trade_settings(monkeypatch)
    mock_result = OkxOrderResult(order_id="999", success=True)
    with patch("hiveflow.cli.execute_trades", return_value=[
        type("R", (), {"order": TradeOrder(symbol="BTC", action="buy", usdt=100.0),
                       "order_id": "999", "success": True, "error_msg": ""})()
    ]):
        result = CliRunner().invoke(app, [
            "trade", "execute",
            "--orders", '[{"symbol":"BTC","action":"buy","usdt":100}]',
        ], input="confirm\n")
    assert result.exit_code == 0
    assert "999" in result.output
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 创建 trade.py**

```python
# src/hiveflow/application/trade.py
"""OKX 现货交易执行用例。"""
from __future__ import annotations
from dataclasses import dataclass
from hiveflow.infrastructure.okx.okx_provider import OkxProvider, OkxTicker


@dataclass(frozen=True)
class TradeOrder:
    symbol: str
    action: str   # buy / sell
    usdt: float


@dataclass
class TradeResult:
    order: TradeOrder
    order_id: str
    success: bool
    error_msg: str = ""


def execute_trades(
    orders: list[TradeOrder],
    api_key: str,
    api_secret: str,
    passphrase: str,
) -> list[TradeResult]:
    """逐个下单，不中断——调用方决定如何处理部分失败。"""
    provider = OkxProvider(api_key=api_key, api_secret=api_secret, passphrase=passphrase)

    # 为卖单预先获取当前价格
    sell_symbols = [o.symbol for o in orders if o.action == "sell"]
    price_map: dict[str, float] = {}
    if sell_symbols:
        inst_ids = [f"{s}-USDT" for s in sell_symbols]
        tickers: list[OkxTicker] = provider.fetch_tickers(inst_ids)
        price_map = {t.symbol: t.last for t in tickers}

    results = []
    for order in orders:
        inst_id = f"{order.symbol}-USDT"
        current_price = price_map.get(order.symbol)
        okx_result = provider.place_market_order(
            inst_id=inst_id,
            side=order.action,
            usdt_amount=order.usdt,
            current_price=current_price,
        )
        results.append(TradeResult(
            order=order,
            order_id=okx_result.order_id,
            success=okx_result.success,
            error_msg=okx_result.error_msg,
        ))
    return results
```

- [ ] **Step 4: 在 cli.py 新增 trade 命令组**

在 import 区域新增：
```python
from hiveflow.application.trade import TradeOrder, execute_trades
```

新增命令组（在 `app.add_typer` 块之前）：

```python
trade_app = typer.Typer(help="交易执行命令。")

@trade_app.command("execute")
def trade_execute_command(
    orders_json: str = typer.Option(..., "--orders", help='订单列表 JSON，格式：[{"symbol":"BTC","action":"buy","usdt":500}]'),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """执行现货市价单（需要 Trade 权限 API Key）。"""
    import json as _json
    settings = Settings()
    if not (settings.okx_trade_api_key and settings.okx_trade_api_secret and settings.okx_trade_passphrase):
        console.print(
            "错误：未配置 OKX Trade API Key。请在 .env 中设置：\n"
            "  HIVEFLOW_OKX_TRADE_API_KEY / _SECRET / _PASSPHRASE",
            style="bold red",
        )
        raise typer.Exit(code=1)

    try:
        raw = _json.loads(orders_json)
        orders = [TradeOrder(symbol=o["symbol"], action=o["action"], usdt=float(o["usdt"])) for o in raw]
    except Exception as e:
        console.print(f"[bold red]错误：订单 JSON 格式无效：{e}[/bold red]")
        raise typer.Exit(code=1)

    console.print("[bold]待执行订单：[/bold]")
    for o in orders:
        action_cn = "买入" if o.action == "buy" else "卖出"
        console.print(f"  {action_cn} {o.symbol}  {o.usdt:.2f} USDT（市价）")

    console.print()
    confirm = typer.prompt("输入 confirm 确认执行，其他任意内容取消")
    if confirm.strip().lower() != "confirm":
        console.print("已取消。")
        raise typer.Exit(code=0)

    console.print("\n执行中...")
    results = execute_trades(
        orders=orders,
        api_key=settings.okx_trade_api_key,
        api_secret=settings.okx_trade_api_secret,
        passphrase=settings.okx_trade_passphrase,
    )

    has_failure = False
    success_ids = []
    for r in results:
        action_cn = "买入" if r.order.action == "buy" else "卖出"
        if r.success:
            console.print(f"  ✅ {action_cn} {r.order.symbol}  {r.order.usdt:.2f} USDT → 订单 ID: {r.order_id}")
            success_ids.append(r.order_id)
        else:
            console.print(f"  ❌ {action_cn} {r.order.symbol}  {r.order.usdt:.2f} USDT → 失败：{r.error_msg}")
            has_failure = True

    if has_failure:
        console.print(f"\n[bold yellow]⚠️  部分订单失败，请在 OKX 手动确认账户状态。成功订单 ID：{', '.join(success_ids)}[/bold yellow]")
        raise typer.Exit(code=1)
    else:
        console.print("\n[bold green]执行完成。[/bold green]")
```

在 `app.add_typer` 块末尾追加：
```python
app.add_typer(trade_app, name="trade")
```

- [ ] **Step 5: 运行测试** `uv run python -m pytest tests/test_trade_execute.py -v`
- [ ] **Step 6: 全量测试** `uv run python -m pytest -q`
- [ ] **Step 7: 提交** `git commit -m "feat: 新增 trade execute 命令（OKX 现货市价单执行）"`

---

## Chunk 5: AI Skills

### Task 9: hiveflow-daily-check Skill

**Files:**
- Create: `~/.agents/skills/hiveflow-daily-check/SKILL.md`

- [ ] **Step 1: 创建 SKILL.md**

```markdown
---
name: hiveflow-daily-check
description: Daily 5-minute portfolio health check for HiveFlow users. Syncs OKX data, checks risk signals, interprets drawdown trends, and gives a one-sentence verdict. Use when user says "check my portfolio", "今日检查", "daily check", or any similar daily review request.
---

# HiveFlow 每日持仓健康检查

每天 5 分钟，三步完成：同步数据 → 风险检查 → 给出结论。

## 执行步骤

### Step 1：同步数据

```bash
uv run hiveflow sync
```

同步当天持仓和价格。若已在当天同步过，可跳过。

### Step 2：检查风险

```bash
uv run hiveflow check --output json
uv run hiveflow positions list --output json
```

### Step 3：解读并给出结论

收到 JSON 后，按以下框架分析：

**风险信号解读：**
- 看 `signals` 数组中每个资产的 `max_drawdown_7d_pct`
- 不要只看单日数字——结合趋势：连续下跌比单日大跌更危险
- DANGER（< -20%）：必须提及，建议用户认真考虑是否需要减仓
- WARNING（-10% ~ -20%）：提醒关注，不必恐慌
- NORMAL（> -10%）：简单带过即可

**USDT 弹药检查：**
- 从 `positions list` 的 `free` 数组中找到 USDT 的 `weight`
- weight < 0.10（10%）：标注"弹药不足"，建议考虑增加稳定币缓冲
- weight > 0.40（40%）：可以提示"弹药充足，可考虑择机建仓"

**结论规则：**
- 无任何告警：一句话说安全，不需要废话
- 有 WARNING：点名资产，提示关注
- 有 DANGER：明确说危险，建议启动 portfolio-advisor 做深度分析

**何时建议升级到 portfolio-advisor：**
- 任意资产出现 DANGER 信号
- 用户主动询问"该怎么调仓"
- USDT 占比极低（< 5%）且有多个 WARNING

## 输出格式

简洁明了，不超过 10 行。示例：

```
今日检查完成 2026-03-16

[结论] ✅ 安全，无需操作

持仓：BTC 44.6%  USDT 54.8%  弹药充足
风险：BTC -3.2% 正常  ETH -8.1% 正常
```

或：

```
今日检查完成 2026-03-16

[结论] ⚠️ 建议关注 ETH — 近7日回撤 -14.2%

持仓：BTC 45%  ETH 30%  USDT 10%  ⚠️ 弹药偏低
风险：BTC -3.2% 正常  ETH -14.2% 注意  SOL -5.1% 正常
建议：观察 ETH 走势，若继续下跌考虑启动 portfolio-advisor。
```
```

- [ ] **Step 2: 验证文件存在** `ls ~/.agents/skills/hiveflow-daily-check/`
- [ ] **Step 3: 提交（本地 skill 文件不在 git 仓库中，无需 git commit）**

---

### Task 10: hiveflow-portfolio-advisor Skill

**Files:**
- Create: `~/.agents/skills/hiveflow-portfolio-advisor/SKILL.md`

- [ ] **Step 1: 创建 SKILL.md**

```markdown
---
name: hiveflow-portfolio-advisor
description: Deep portfolio analysis and rebalancing for HiveFlow users. Runs backtests on candidate allocations, recommends optimal allocation based on investment theory, generates rebalancing orders, and executes on OKX after user confirmation. Use when user says "调仓", "rebalance", "分析配比", "我该怎么动", or any request for portfolio decision-making beyond daily risk check.
---

# HiveFlow Portfolio Advisor

深度决策工具。从回测配比到 OKX 执行，全程辅助。

## 前置条件

确保已执行 `hiveflow sync --days 30` 积累至少 30 天行情数据。

## 执行流程

### Step 1：获取当前自由持仓

```bash
uv run hiveflow positions list --output json
```

从 `free` 数组提取持仓资产列表（排除 USDT）。

### Step 2：生成候选配比并写入策略

根据持仓资产，生成三组候选配比：

**生成规则：**
- USDT 最低 10%（弹药底线，不可低于此值）
- 单资产上限 60%（避免过度集中）
- BTC 作为核心资产，建议权重不低于 20%

**三个模板（根据实际持仓资产动态调整权重，确保加总为 1）：**

| 模板 | 特点 | USDT | BTC | 其他 |
|---|---|---|---|---|
| 激进版 | 高风险高收益 | 10% | 50%+ | 剩余均分 |
| 均衡版 | 风险收益平衡 | 20% | 40% | 剩余均分 |
| 保守版 | 低风险稳健 | 40% | 30% | 剩余均分 |

对每个配比执行：
```bash
uv run hiveflow targets import --strategy "激进版" --mode replace  # 通过 CSV 或其他方式写入配比
uv run hiveflow backtest run --strategy "激进版"
```

### Step 3：比较回测结果

```bash
uv run hiveflow backtest list --output json
```

展示对比表格（只看最近三次回测）：

| 策略 | 总收益 | 最大回撤 | 夏普比率 |
|---|---|---|---|
| 激进版 | ... | ... | ... |
| 均衡版 | ... | ... | ... |
| 保守版 | ... | ... | ... |

### Step 4：给出推荐并说明理由

**投资理论框架（按优先级应用）：**

1. **回撤优先**：最大回撤是第一过滤条件。加密市场暴跌频繁，-30% 以下的配比要明确警示风险。优先推荐最大回撤控制在 -25% 以内的配比。

2. **风险调整收益（夏普比率）**：在同等回撤约束下，优先选夏普更高的。夏普 > 1.0 为优秀，0.5~1.0 为可接受，< 0.5 需谨慎。

3. **USDT 弹药原则**：保留 USDT 不是保守，是保留机会。市场突然下跌时，手头有 USDT 才能低位补仓。

4. **分散但不稀释**：3-5 个资产足够。超过 5 个资产时，权重过小的资产（< 5%）等于没有。

**推荐格式示例：**
```
推荐：均衡版（BTC 40% ETH 25% SOL 15% USDT 20%）

理由：
- 最大回撤 -18%，低于激进版的 -28%，风险可控
- 夏普比率 1.35，是三个配比中最高的
- USDT 20% 保留足够弹药

激进版回撤过大（-28%），在加密市场波动环境下不建议。
保守版总收益明显低，当前持仓中高波动资产较多时意义不大。
```

**帮助用户了解自己的风险偏好：**
每次分析结束后问一句：
> "这个配比的最大回撤 -18% 你能接受吗？如果市值一个月内从 10 万跌到 8.2 万，你会慌吗？"

用户的回答会帮助你在下次推荐时更准确地匹配他的风险偏好。

**其他策略科普（仅教育）：**
- 动量策略：过去表现好的资产持续持有，适合牛市
- 均值回归：跌多了买，涨多了卖，适合震荡市
- 网格交易：横盘震荡时效果好，当前系统不执行，可以建议手动在 OKX 设置
- 合约/杠杆：放大收益也放大风险，不在本系统范围内，高风险谨慎参与

### Step 5：用户选定配比后设置目标

```bash
uv run hiveflow targets set-from-backtest <backtest_id>
```

### Step 6：预览调仓建议

```bash
uv run hiveflow rebalance preview --output json
```

分析 `suggestions` 数组，生成人类可读的调仓报告：
- HIGH priority：需要立即处理
- MEDIUM：建议处理
- LOW：可选

### Step 7：生成订单并确认执行

将调仓建议转换为订单列表，展示给用户：

```
调仓计划：
  买入 ETH  约 500 USDT（当前 25% → 目标 30%）
  卖出 SOL  约 200 USDT（当前 20% → 目标 15%）
  保留 BTC（偏差 < 2%，无需调整）

总交易量：约 700 USDT
预估手续费：~0.1%（约 0.7 USDT）

确认执行？
```

用户确认后：
```bash
uv run hiveflow trade execute --orders '[{"symbol":"ETH","action":"buy","usdt":500},{"symbol":"SOL","action":"sell","usdt":200}]'
```

### Step 8：执行后汇报

展示执行结果，记录本次调仓决策。

## 注意事项

- 执行前确保 `.env` 中已配置 Trade API Key（`HIVEFLOW_OKX_TRADE_API_KEY` 等）
- 网格持仓中的资产不计入调仓计算，请从 `positions list` 的 `grid` 区块确认
- 市价单会产生滑点，实际成交价格可能与预览略有偏差
- 若执行部分失败，系统会给出成功的订单 ID，请在 OKX 手动确认账户状态
```

- [ ] **Step 2: 验证文件存在** `ls ~/.agents/skills/hiveflow-portfolio-advisor/`

---

## 验收

```bash
# 全量测试
uv run python -m pytest -q  # 期望全部通过

# 命令验证
uv run hiveflow positions list        # 显示自由持仓 + 网格持仓（有网格时）
uv run hiveflow backtest run --help   # --file 显示为可选
uv run hiveflow targets set-from-backtest --help
uv run hiveflow trade execute --help
uv run hiveflow trade execute --orders '[]'  # 应提示 Trade Key 未配置

# Skill 验证
ls ~/.agents/skills/hiveflow-daily-check/
ls ~/.agents/skills/hiveflow-portfolio-advisor/
```
