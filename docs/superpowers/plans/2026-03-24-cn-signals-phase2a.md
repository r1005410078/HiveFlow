# A 股特有信号 Phase 2-A 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 A 股特有信号：个股层面（PE/PB、涨跌停触发）和市场层面（北向资金、融资余额、全市场涨跌停家数），以腾讯行情为主数据源、akshare 为补充/回退。

**Architecture:** 新增 `CNStockSignal`、`CNMarketSignal` 两个 SQLModel 实体（domain 层），`CNSignalProvider`（infrastructure 层，腾讯+akshare 双后端），`build_cn_stock_signal`/`build_cn_market_signal`（application 层），以及 CLI 子命令 `signal cn-stock` / `signal cn-market`。全部为加法，不动现有 `SignalSnapshot` 路径。

**Tech Stack:** Python 3.11+, SQLModel, SQLite, typer, akshare>=1.14.0, urllib（标准库，腾讯行情）

---

## 文件清单

| 操作 | 路径 | 职责 |
|------|------|------|
| 新建 | `src/hiveflow/domain/cn_signals.py` | CNStockSignal、CNMarketSignal 实体 |
| 新建 | `src/hiveflow/infrastructure/cn_signal_provider.py` | 腾讯+akshare 双后端信号获取 |
| 新建 | `src/hiveflow/application/cn_signals.py` | build_cn_stock_signal、build_cn_market_signal |
| 新建 | `tests/test_cn_signals.py` | 所有新增测试 |
| 修改 | `src/hiveflow/db.py` | 新增两张表的 CREATE TABLE IF NOT EXISTS |
| 修改 | `src/hiveflow/cli.py` | 新增 cn-stock、cn-market 子命令 |

---

## Chunk 1: Domain 实体与数据库建表

### Task 1: CNStockSignal 与 CNMarketSignal 实体

**Files:**
- Create: `src/hiveflow/domain/cn_signals.py`
- Test: `tests/test_cn_signals.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cn_signals.py
"""A 股特有信号实体测试。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from hiveflow.domain.cn_signals import CNMarketSignal, CNStockSignal


def test_cn_stock_signal_defaults() -> None:
    """CNStockSignal 默认值正确，market 为 cn_a_share。"""
    ts = datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc)
    sig = CNStockSignal(symbol="000001.SZ", date="2026-03-24", timestamp=ts)
    assert sig.market == "cn_a_share"
    assert sig.pe_ratio is None
    assert sig.pb_ratio is None
    assert sig.limit_up_hit is None
    assert sig.limit_down_hit is None


def test_cn_market_signal_defaults() -> None:
    """CNMarketSignal 默认值正确。"""
    ts = datetime(2026, 3, 24, 7, 0, 0, tzinfo=timezone.utc)
    sig = CNMarketSignal(date="2026-03-24", timestamp=ts)
    assert sig.northbound_net_flow is None
    assert sig.margin_balance is None
    assert sig.limit_up_count is None
    assert sig.limit_down_count is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：`ImportError: cannot import name 'CNStockSignal'`

- [ ] **Step 3: 实现实体**

```python
# src/hiveflow/domain/cn_signals.py
"""A 股特有信号实体：个股级（CNStockSignal）和市场级（CNMarketSignal）。"""
from __future__ import annotations

from datetime import datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class CNStockSignal(SQLModel, table=True):
    """个股 A 股特有信号快照（PE/PB、涨跌停触发）。

    唯一约束：同一 symbol 同一日期只保留最新一条（覆盖写入）。
    涨跌停检测已知限制：仅覆盖主板非 ST 股 ±10%，ST/创业板/科创板/北交所不适用。
    """

    __table_args__ = (
        UniqueConstraint("symbol", "date", name="uq_cn_stock_signal_symbol_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    date: str                           # "YYYY-MM-DD"，唯一约束用
    timestamp: datetime                 # 信号时间（UTC）
    market: str = "cn_a_share"
    pe_ratio: float | None = None       # 市盈率（TTM）
    pb_ratio: float | None = None       # 市净率
    limit_up_hit: bool | None = None    # 当日触及涨停
    limit_down_hit: bool | None = None  # 当日触及跌停


class CNMarketSignal(SQLModel, table=True):
    """市场级 A 股信号（北向资金、融资余额、全市场涨跌停家数）。

    唯一约束：同一日期只保留最新一条（覆盖写入）。
    """

    __table_args__ = (
        UniqueConstraint("date", name="uq_cn_market_signal_date"),
    )

    id: int | None = Field(default=None, primary_key=True)
    date: str                                             # "YYYY-MM-DD"
    timestamp: datetime                                   # 信号时间（UTC）
    northbound_net_flow: float | None = None              # 北向资金净流入（亿元）
    margin_balance: float | None = None                   # 融资余额（亿元，沪深合计）
    limit_up_count: int | None = None                     # 全市场涨停家数
    limit_down_count: int | None = None                   # 全市场跌停家数
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：`2 passed`

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/domain/cn_signals.py tests/test_cn_signals.py
git commit -m "feat: 新增 CNStockSignal 和 CNMarketSignal 实体"
```

---

### Task 2: 数据库建表

**Files:**
- Modify: `src/hiveflow/db.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

在 `tests/test_cn_signals.py` 末尾追加：

```python
def test_cn_signal_tables_created(tmp_path) -> None:
    """create_all_tables 后两张新表存在。"""
    import sqlite3
    from hiveflow.config import Settings
    from hiveflow.db import create_all_tables

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)
    create_all_tables(settings)

    conn = sqlite3.connect(str(tmp_path / "hiveflow.db"))
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()

    assert "cnstocksignal" in tables
    assert "cnmarketsignal" in tables
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py::test_cn_signal_tables_created -v
```
预期：`AssertionError: assert 'cnstocksignal' in tables`

- [ ] **Step 3: 修改 db.py 导入新实体**

在 `src/hiveflow/db.py` 的现有 domain 导入区（找到其他实体的导入行）追加：

```python
from hiveflow.domain.cn_signals import CNMarketSignal, CNStockSignal  # noqa: F401
```

（`create_all_tables` 调用 `SQLModel.metadata.create_all(engine)`，导入实体后会自动建表。）

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：`3 passed`

- [ ] **Step 5: 全量回归**

```bash
uv run pytest -q
```
预期：全部 passed，无新增 failure。

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/db.py tests/test_cn_signals.py
git commit -m "feat: db.py 导入新实体，自动建 cnstocksignal / cnmarketsignal 表"
```

---

## Chunk 2: CNSignalProvider（Infrastructure 层）

### Task 3: 腾讯行情涨跌停检测

**Files:**
- Create: `src/hiveflow/infrastructure/cn_signal_provider.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

```python
def test_tencent_limit_hit_detection() -> None:
    """_detect_limit_from_tencent：涨停/跌停/正常三种情况。"""
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    p = CNSignalProvider()
    # 涨停：last >= prev_close * 1.095
    assert p._detect_limit_from_prices(11.0, 10.0) == (True, False)
    # 跌停：last <= prev_close * 0.905
    assert p._detect_limit_from_prices(9.0, 10.0) == (False, True)
    # 正常
    assert p._detect_limit_from_prices(10.3, 10.0) == (False, False)


def test_to_tencent_code_in_signal_provider() -> None:
    """_to_tencent_code 转换格式正确。"""
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    p = CNSignalProvider()
    assert p._to_tencent_code("000001.SZ") == "sz000001"
    assert p._to_tencent_code("600000.SH") == "sh600000"
    assert p._to_tencent_code("830017.BJ") == "bj830017"


def test_fetch_stock_signal_tencent_success(monkeypatch) -> None:
    """腾讯行情正常时，fetch_stock_signal 返回含涨跌停的 dict。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    # 构造 45 字段腾讯响应：parts[3]=10.50（正常），parts[4]=10.00，parts[30]=时间戳
    parts = [""] * 45
    parts[3] = "10.50"   # last
    parts[4] = "10.00"   # prev_close
    parts[30] = "20260324150000"
    mock_line = 'v_sz000001="' + "~".join(parts) + '";\n'

    class _FakeResp:
        def read(self): return mock_line.encode("gbk")
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _FakeResp())

    p = CNSignalProvider()
    result = p.fetch_stock_signal("000001.SZ")

    assert result["limit_up_hit"] is False
    assert result["limit_down_hit"] is False
    assert result["timestamp"] is not None


def test_fetch_stock_signal_tencent_limit_up(monkeypatch) -> None:
    """last >= prev_close * 1.095 时，limit_up_hit 为 True。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    parts = [""] * 45
    parts[3] = "11.00"   # last（涨停：11.00 >= 10.00 * 1.095）
    parts[4] = "10.00"
    parts[30] = "20260324150000"
    mock_line = 'v_sz000001="' + "~".join(parts) + '";\n'

    class _FakeResp:
        def read(self): return mock_line.encode("gbk")
        def __enter__(self): return self
        def __exit__(self, *_): pass

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **kw: _FakeResp())

    p = CNSignalProvider()
    result = p.fetch_stock_signal("000001.SZ")
    assert result["limit_up_hit"] is True
    assert result["limit_down_hit"] is False


def test_fetch_stock_signal_tencent_failure_returns_none_fields(monkeypatch) -> None:
    """腾讯连接失败时，limit 字段为 None，不抛异常。"""
    import urllib.request
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(ConnectionError("timeout"))
    )

    p = CNSignalProvider()
    result = p.fetch_stock_signal("000001.SZ")
    assert result["limit_up_hit"] is None
    assert result["limit_down_hit"] is None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "tencent or to_tencent_code" -v
```
预期：`ImportError: cannot import name 'CNSignalProvider'`

- [ ] **Step 3: 实现 CNSignalProvider（腾讯部分）**

```python
# src/hiveflow/infrastructure/cn_signal_provider.py
"""A 股特有信号提供者（腾讯行情主 + akshare 补充/回退）。"""
from __future__ import annotations

import re
import urllib.request
import warnings
from datetime import datetime, timezone

from hiveflow.config import Settings

# 模块级可选导入（支持 patch）
try:
    import akshare  # type: ignore[import]
except ImportError:
    akshare = None  # type: ignore[assignment]


class CNSignalProvider:
    """A 股特有信号获取器。

    使用 settings.cn_market_data_source 和 settings.tushare_token 配置数据源。
    腾讯行情（qt.gtimg.cn）用于实时涨跌停检测；
    akshare 用于 PE/PB、北向资金、融资余额等深度数据（无腾讯回退）。
    任一数据源失败时对应字段置 None，不中断整体流程。
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    # ------------------------------------------------------------------ #
    # 公开接口
    # ------------------------------------------------------------------ #

    def fetch_stock_signal(self, symbol: str) -> dict:
        """获取个股信号字段 dict。字段缺失时值为 None。

        返回键：limit_up_hit, limit_down_hit, pe_ratio, pb_ratio, timestamp
        """
        limit_up, limit_down, ts = self._fetch_limit_hit_tencent(symbol)
        if limit_up is None:
            # 腾讯失败，尝试 akshare 回退
            limit_up, limit_down = self._fetch_limit_hit_akshare(symbol)

        pe, pb = self._fetch_pe_pb_akshare(symbol)

        return {
            "limit_up_hit": limit_up,
            "limit_down_hit": limit_down,
            "pe_ratio": pe,
            "pb_ratio": pb,
            "timestamp": ts or datetime.now(tz=timezone.utc),
        }

    def fetch_market_signal(self) -> dict:
        """获取市场级信号字段 dict。字段缺失时值为 None。

        返回键：northbound_net_flow, margin_balance,
                limit_up_count, limit_down_count, timestamp
        """
        northbound = self._fetch_northbound_akshare()
        margin = self._fetch_margin_balance_akshare()
        up_count, down_count = self._fetch_limit_counts_akshare()

        return {
            "northbound_net_flow": northbound,
            "margin_balance": margin,
            "limit_up_count": up_count,
            "limit_down_count": down_count,
            "timestamp": datetime.now(tz=timezone.utc),
        }

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def _to_tencent_code(self, symbol: str) -> str:
        """000001.SZ → sz000001，600000.SH → sh600000，830017.BJ → bj830017。"""
        if "." in symbol:
            code, suffix = symbol.upper().rsplit(".", 1)
            prefix = {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suffix, "sz")
            return f"{prefix}{code}"
        return ("sh" if symbol.startswith("6") else "sz") + symbol

    def _detect_limit_from_prices(
        self, last: float, prev_close: float
    ) -> tuple[bool, bool]:
        """根据最新价和昨收价判断是否触及涨跌停（主板非 ST ±10%）。"""
        return (last >= prev_close * 1.095, last <= prev_close * 0.905)

    # ------------------------------------------------------------------ #
    # 腾讯后端
    # ------------------------------------------------------------------ #

    def _fetch_limit_hit_tencent(
        self, symbol: str
    ) -> tuple[bool | None, bool | None, datetime | None]:
        """从腾讯行情拉取涨跌停状态。失败时三值均返回 None。"""
        code = self._to_tencent_code(symbol)
        url = f"http://qt.gtimg.cn/q={code}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read().decode("gbk")
        except Exception as e:
            warnings.warn(f"腾讯行情拉取 {symbol!r} 失败: {type(e).__name__}: {e}")
            return None, None, None

        try:
            lines = [ln for ln in raw.strip().splitlines() if ln.strip()]
            if not lines:
                return None, None, None
            match = re.search(r'"([^"]+)"', lines[0])
            if not match:
                return None, None, None
            parts = match.group(1).split("~")
            if len(parts) < 35:
                return None, None, None

            last = float(parts[3])
            prev_close = float(parts[4])
            ts_str = parts[30].strip()
            ts = (
                datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                if len(ts_str) >= 14
                else datetime.now(tz=timezone.utc)
            )
            limit_up, limit_down = self._detect_limit_from_prices(last, prev_close)
            return limit_up, limit_down, ts
        except (IndexError, ValueError) as e:
            warnings.warn(f"腾讯行情解析 {symbol!r} 失败: {e}")
            return None, None, None
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -k "tencent or to_tencent_code or limit_hit" -v
```
预期：`6 passed`

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/infrastructure/cn_signal_provider.py tests/test_cn_signals.py
git commit -m "feat: CNSignalProvider 腾讯行情涨跌停检测"
```

---

### Task 4: akshare 后端（PE/PB、北向资金、融资余额、涨跌停家数）

**Files:**
- Modify: `src/hiveflow/infrastructure/cn_signal_provider.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

```python
def test_fetch_pe_pb_akshare_success(monkeypatch) -> None:
    """akshare pe/pb 拉取成功时返回浮点数。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = type("FakeAK", (), {})()
    mock_ak.stock_a_lg_indicator = lambda symbol: pd.DataFrame({
        "pe_ttm": [8.32],
        "pb": [0.76],
    })
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        p = CNSignalProvider()
        pe, pb = p._fetch_pe_pb_akshare("000001.SZ")
    finally:
        mod.akshare = original

    assert pe == pytest.approx(8.32)
    assert pb == pytest.approx(0.76)


def test_fetch_pe_pb_akshare_failure_returns_none(monkeypatch) -> None:
    """akshare 抛异常时 pe/pb 均为 None。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = type("FakeAK", (), {})()
    mock_ak.stock_a_lg_indicator = lambda symbol: (_ for _ in ()).throw(Exception("error"))
    original = mod.akshare
    mod.akshare = mock_ak
    try:
        p = CNSignalProvider()
        pe, pb = p._fetch_pe_pb_akshare("000001.SZ")
    finally:
        mod.akshare = original

    assert pe is None
    assert pb is None


def test_fetch_market_signal_success(monkeypatch) -> None:
    """fetch_market_signal 全字段正常时返回完整 dict。"""
    import pandas as pd
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = type("FakeAK", (), {})()
    # 北向资金
    mock_ak.stock_em_hsgt_north_net_flow_in = lambda symbol: pd.DataFrame({
        "date": ["2026-03-24"],
        "value": [32.5],
    })
    # 融资余额（沪+深）
    mock_ak.stock_margin_detail_sse = lambda date: pd.DataFrame({
        "融资余额": [8000.0],
    })
    mock_ak.stock_margin_detail_szse = lambda date: pd.DataFrame({
        "融资余额": [6832.6],
    })
    # 涨跌停
    mock_ak.stock_zt_pool_em = lambda date: pd.DataFrame({"代码": ["000001", "000002"]})
    mock_ak.stock_zt_pool_dtgc_em = lambda date: pd.DataFrame({"代码": ["600001"]})

    original = mod.akshare
    mod.akshare = mock_ak
    try:
        p = CNSignalProvider()
        result = p.fetch_market_signal()
    finally:
        mod.akshare = original

    assert result["northbound_net_flow"] == pytest.approx(32.5)
    assert result["margin_balance"] == pytest.approx(14832.6)
    assert result["limit_up_count"] == 2
    assert result["limit_down_count"] == 1


def test_fetch_market_signal_partial_none(monkeypatch) -> None:
    """akshare 部分接口失败时，失败字段为 None，其余正常，不抛异常。"""
    import hiveflow.infrastructure.cn_signal_provider as mod
    from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider

    mock_ak = type("FakeAK", (), {})()
    mock_ak.stock_em_hsgt_north_net_flow_in = lambda symbol: (_ for _ in ()).throw(Exception("fail"))
    mock_ak.stock_margin_detail_sse = lambda date: (_ for _ in ()).throw(Exception("fail"))
    mock_ak.stock_margin_detail_szse = lambda date: (_ for _ in ()).throw(Exception("fail"))
    mock_ak.stock_zt_pool_em = lambda date: (_ for _ in ()).throw(Exception("fail"))
    mock_ak.stock_zt_pool_dtgc_em = lambda date: (_ for _ in ()).throw(Exception("fail"))

    original = mod.akshare
    mod.akshare = mock_ak
    try:
        p = CNSignalProvider()
        result = p.fetch_market_signal()
    finally:
        mod.akshare = original

    assert result["northbound_net_flow"] is None
    assert result["margin_balance"] is None
    assert result["limit_up_count"] is None
    assert result["limit_down_count"] is None
    assert result["timestamp"] is not None
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "akshare or market_signal" -v
```
预期：`AttributeError: '_fetch_pe_pb_akshare'`

- [ ] **Step 3: 在 CNSignalProvider 追加 akshare 方法**

在 `cn_signal_provider.py` 的 `_fetch_limit_hit_tencent` 方法之后追加：

```python
    # ------------------------------------------------------------------ #
    # akshare 后端
    # ------------------------------------------------------------------ #

    def _get_akshare(self):
        """获取模块级 akshare（支持测试 patch）。"""
        import hiveflow.infrastructure.cn_signal_provider as _mod
        _ak = _mod.akshare
        if _ak is None:
            raise ImportError("akshare 未安装。运行: pip install akshare")
        return _ak

    def _fetch_limit_hit_akshare(
        self, symbol: str
    ) -> tuple[bool | None, bool | None]:
        """akshare 回退：当日 K 线推断涨跌停。"""
        try:
            _ak = self._get_akshare()
            code = symbol.split(".")[0] if "." in symbol else symbol
            from datetime import date as _date
            today = _date.today().strftime("%Y%m%d")
            df = _ak.stock_zh_a_hist(
                symbol=code, period="daily",
                start_date=today, end_date=today, adjust="qfq"
            )
            if df is None or df.empty:
                return None, None
            row = df.iloc[-1]
            prev_close = float(row["收盘"]) / (1 + float(row["涨跌幅"]) / 100)
            last = float(row["收盘"])
            return self._detect_limit_from_prices(last, prev_close)
        except Exception as e:
            warnings.warn(f"akshare 回退涨跌停 {symbol!r} 失败: {e}")
            return None, None

    def _fetch_pe_pb_akshare(self, symbol: str) -> tuple[float | None, float | None]:
        """akshare 获取 PE/PB。"""
        try:
            _ak = self._get_akshare()
            code = symbol.split(".")[0] if "." in symbol else symbol
            df = _ak.stock_a_lg_indicator(symbol=code)
            if df is None or df.empty:
                return None, None
            row = df.iloc[-1]
            pe = float(row["pe_ttm"]) if "pe_ttm" in df.columns else None
            pb = float(row["pb"]) if "pb" in df.columns else None
            return pe, pb
        except Exception as e:
            warnings.warn(f"akshare PE/PB {symbol!r} 失败: {e}")
            return None, None

    def _fetch_northbound_akshare(self) -> float | None:
        """akshare 获取北向资金净流入（亿元）。"""
        try:
            _ak = self._get_akshare()
            df = _ak.stock_em_hsgt_north_net_flow_in(symbol="北向资金")
            if df is None or df.empty:
                return None
            return float(df.iloc[-1]["value"])
        except Exception as e:
            warnings.warn(f"akshare 北向资金失败: {e}")
            return None

    def _fetch_margin_balance_akshare(self) -> float | None:
        """akshare 获取沪深融资余额合计（亿元）。"""
        try:
            _ak = self._get_akshare()
            from datetime import date as _date
            today = _date.today().strftime("%Y%m%d")
            df_sse = _ak.stock_margin_detail_sse(date=today)
            df_szse = _ak.stock_margin_detail_szse(date=today)
            total = 0.0
            if df_sse is not None and not df_sse.empty and "融资余额" in df_sse.columns:
                total += float(df_sse["融资余额"].iloc[0])
            if df_szse is not None and not df_szse.empty and "融资余额" in df_szse.columns:
                total += float(df_szse["融资余额"].iloc[0])
            return total if total > 0 else None
        except Exception as e:
            warnings.warn(f"akshare 融资余额失败: {e}")
            return None

    def _fetch_limit_counts_akshare(self) -> tuple[int | None, int | None]:
        """akshare 获取全市场涨停/跌停家数。"""
        try:
            _ak = self._get_akshare()
            from datetime import date as _date
            today = _date.today().strftime("%Y%m%d")
            df_up = _ak.stock_zt_pool_em(date=today)
            up_count = len(df_up) if df_up is not None else None
        except Exception as e:
            warnings.warn(f"akshare 涨停家数失败: {e}")
            up_count = None

        try:
            _ak = self._get_akshare()
            from datetime import date as _date
            today = _date.today().strftime("%Y%m%d")
            df_down = _ak.stock_zt_pool_dtgc_em(date=today)
            down_count = len(df_down) if df_down is not None else None
        except Exception as e:
            warnings.warn(f"akshare 跌停家数失败: {e}")
            down_count = None

        return up_count, down_count
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：全部 passed（目前约 13 个测试）

- [ ] **Step 5: 全量回归**

```bash
uv run pytest -q
```
预期：全部 passed，无新增 failure。

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/infrastructure/cn_signal_provider.py tests/test_cn_signals.py
git commit -m "feat: CNSignalProvider akshare 后端（PE/PB、北向、融资、涨跌停）"
```

---

## Chunk 3: Application 层

### Task 5: build_cn_stock_signal

**Files:**
- Create: `src/hiveflow/application/cn_signals.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

```python
def test_build_cn_stock_signal_writes_db(tmp_path) -> None:
    """build_cn_stock_signal 落库并返回 CNStockSignal 实体。"""
    from unittest.mock import patch
    from hiveflow.config import Settings
    from hiveflow.application.cn_signals import build_cn_stock_signal

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)

    mock_data = {
        "limit_up_hit": False,
        "limit_down_hit": False,
        "pe_ratio": 8.32,
        "pb_ratio": 0.76,
        "timestamp": __import__("datetime").datetime(2026, 3, 24, 7, 0, tzinfo=__import__("datetime").timezone.utc),
    }

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider.fetch_stock_signal",
        return_value=mock_data,
    ):
        result = build_cn_stock_signal("000001.SZ", settings=settings)

    assert result.symbol == "000001.SZ"
    assert result.pe_ratio == pytest.approx(8.32)
    assert result.market == "cn_a_share"
    assert result.id is not None


def test_build_cn_stock_signal_dedup_overwrite(tmp_path) -> None:
    """同一 symbol 同一日期重复调用，覆盖写入不堆积。"""
    from unittest.mock import patch
    from hiveflow.config import Settings
    from hiveflow.application.cn_signals import build_cn_stock_signal
    from hiveflow.db import get_session
    from hiveflow.domain.cn_signals import CNStockSignal
    from sqlmodel import select

    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)

    import datetime as dt
    ts = dt.datetime(2026, 3, 24, 7, 0, tzinfo=dt.timezone.utc)
    mock_data = {"limit_up_hit": False, "limit_down_hit": False,
                 "pe_ratio": 8.0, "pb_ratio": 0.7, "timestamp": ts}

    with patch("hiveflow.application.cn_signals.CNSignalProvider.fetch_stock_signal",
               return_value=mock_data):
        build_cn_stock_signal("000001.SZ", settings=settings)
        build_cn_stock_signal("000001.SZ", settings=settings)

    with get_session(settings) as session:
        rows = session.exec(
            select(CNStockSignal).where(CNStockSignal.symbol == "000001.SZ")
        ).all()
    assert len(rows) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "build_cn_stock" -v
```
预期：`ImportError: cannot import name 'build_cn_stock_signal'`

- [ ] **Step 3: 实现 build_cn_stock_signal**

```python
# src/hiveflow/application/cn_signals.py
"""A 股特有信号应用层：build_cn_stock_signal、build_cn_market_signal。"""
from __future__ import annotations

from datetime import datetime, timezone

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.cn_signals import CNMarketSignal, CNStockSignal
from hiveflow.infrastructure.cn_signal_provider import CNSignalProvider
from sqlmodel import select


def build_cn_stock_signal(
    symbol: str,
    settings: Settings | None = None,
) -> CNStockSignal:
    """拉取个股 A 股特有信号并落库（同一 symbol 同一日期覆盖写入）。"""
    s = settings or Settings()
    create_all_tables(s)

    provider = CNSignalProvider(settings=s)
    data = provider.fetch_stock_signal(symbol)

    ts: datetime = data.get("timestamp") or datetime.now(tz=timezone.utc)
    date_str = ts.strftime("%Y-%m-%d")

    row = CNStockSignal(
        symbol=symbol.upper(),
        date=date_str,
        timestamp=ts,
        pe_ratio=data.get("pe_ratio"),
        pb_ratio=data.get("pb_ratio"),
        limit_up_hit=data.get("limit_up_hit"),
        limit_down_hit=data.get("limit_down_hit"),
    )

    with get_session(s) as session:
        # 覆盖写入：删除同 symbol + date 的旧记录
        existing = session.exec(
            select(CNStockSignal).where(
                CNStockSignal.symbol == row.symbol,
                CNStockSignal.date == date_str,
            )
        ).all()
        for old in existing:
            session.delete(old)
        session.add(row)
        session.commit()
        session.refresh(row)

    return row
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -k "build_cn_stock" -v
```
预期：`2 passed`

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/application/cn_signals.py tests/test_cn_signals.py
git commit -m "feat: build_cn_stock_signal 落库实现（覆盖写入）"
```

---

### Task 6: build_cn_market_signal

**Files:**
- Modify: `src/hiveflow/application/cn_signals.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

```python
def test_build_cn_market_signal_writes_db(tmp_path) -> None:
    """build_cn_market_signal 落库并返回 CNMarketSignal 实体。"""
    from unittest.mock import patch
    from hiveflow.config import Settings
    from hiveflow.application.cn_signals import build_cn_market_signal

    import datetime as dt
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)

    ts = dt.datetime(2026, 3, 24, 7, 30, tzinfo=dt.timezone.utc)
    mock_data = {
        "northbound_net_flow": 32.5,
        "margin_balance": 14832.6,
        "limit_up_count": 43,
        "limit_down_count": 12,
        "timestamp": ts,
    }

    with patch(
        "hiveflow.application.cn_signals.CNSignalProvider.fetch_market_signal",
        return_value=mock_data,
    ):
        result = build_cn_market_signal(settings=settings)

    assert result.northbound_net_flow == pytest.approx(32.5)
    assert result.limit_up_count == 43
    assert result.id is not None


def test_build_cn_market_signal_dedup_overwrite(tmp_path) -> None:
    """同一日期重复调用，覆盖写入不堆积。"""
    from unittest.mock import patch
    from hiveflow.config import Settings
    from hiveflow.application.cn_signals import build_cn_market_signal
    from hiveflow.db import get_session
    from hiveflow.domain.cn_signals import CNMarketSignal
    from sqlmodel import select

    import datetime as dt
    db_url = f"sqlite:///{tmp_path / 'hiveflow.db'}"
    settings = Settings(database_url=db_url)

    ts = dt.datetime(2026, 3, 24, 7, 30, tzinfo=dt.timezone.utc)
    mock_data = {"northbound_net_flow": 10.0, "margin_balance": 1000.0,
                 "limit_up_count": 5, "limit_down_count": 2, "timestamp": ts}

    with patch("hiveflow.application.cn_signals.CNSignalProvider.fetch_market_signal",
               return_value=mock_data):
        build_cn_market_signal(settings=settings)
        build_cn_market_signal(settings=settings)

    with get_session(settings) as session:
        rows = session.exec(select(CNMarketSignal)).all()
    assert len(rows) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "build_cn_market" -v
```
预期：`ImportError: cannot import name 'build_cn_market_signal'`

- [ ] **Step 3: 在 cn_signals.py 追加 build_cn_market_signal**

```python
def build_cn_market_signal(
    settings: Settings | None = None,
) -> CNMarketSignal:
    """拉取市场级 A 股信号并落库（同一日期覆盖写入）。"""
    s = settings or Settings()
    create_all_tables(s)

    provider = CNSignalProvider(settings=s)
    data = provider.fetch_market_signal()

    ts: datetime = data.get("timestamp") or datetime.now(tz=timezone.utc)
    date_str = ts.strftime("%Y-%m-%d")

    row = CNMarketSignal(
        date=date_str,
        timestamp=ts,
        northbound_net_flow=data.get("northbound_net_flow"),
        margin_balance=data.get("margin_balance"),
        limit_up_count=data.get("limit_up_count"),
        limit_down_count=data.get("limit_down_count"),
    )

    with get_session(s) as session:
        existing = session.exec(
            select(CNMarketSignal).where(CNMarketSignal.date == date_str)
        ).all()
        for old in existing:
            session.delete(old)
        session.add(row)
        session.commit()
        session.refresh(row)

    return row
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：全部 passed（约 17 个）

- [ ] **Step 5: 全量回归**

```bash
uv run pytest -q
```
预期：全部 passed。

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/application/cn_signals.py tests/test_cn_signals.py
git commit -m "feat: build_cn_market_signal 落库实现（覆盖写入）"
```

---

## Chunk 4: CLI 命令

### Task 7: signal cn-stock 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cn_signals.py`（追加）

CLI 文件很大，操作要谨慎。找到 `@signal_app.command("snapshot")` 所在位置，在同一命令组中追加新命令。

- [ ] **Step 1: 追加测试**

```python
def test_cli_cn_stock_text_output(tmp_path) -> None:
    """signal cn-stock 文本输出含所有关键字段，None 显示 N/A。"""
    from typer.testing import CliRunner
    from unittest.mock import patch
    from hiveflow.cli import app
    import datetime as dt

    runner = CliRunner()
    ts = dt.datetime(2026, 3, 24, 7, 0, tzinfo=dt.timezone.utc)

    from hiveflow.domain.cn_signals import CNStockSignal
    mock_result = CNStockSignal(
        id=1, symbol="000001.SZ", date="2026-03-24", timestamp=ts,
        pe_ratio=8.32, pb_ratio=0.76,
        limit_up_hit=False, limit_down_hit=False,
    )

    with patch("hiveflow.cli.build_cn_stock_signal", return_value=mock_result):
        result = runner.invoke(app, ["signal", "cn-stock", "000001.SZ"])

    assert result.exit_code == 0
    assert "000001.SZ" in result.output
    assert "8.32" in result.output
    assert "0.76" in result.output


def test_cli_cn_stock_json_output(tmp_path) -> None:
    """signal cn-stock --output json 输出合法 JSON。"""
    import json
    from typer.testing import CliRunner
    from unittest.mock import patch
    from hiveflow.cli import app
    import datetime as dt

    runner = CliRunner()
    ts = dt.datetime(2026, 3, 24, 7, 0, tzinfo=dt.timezone.utc)

    from hiveflow.domain.cn_signals import CNStockSignal
    mock_result = CNStockSignal(
        id=1, symbol="000001.SZ", date="2026-03-24", timestamp=ts,
        pe_ratio=None, pb_ratio=None,
        limit_up_hit=True, limit_down_hit=False,
    )

    with patch("hiveflow.cli.build_cn_stock_signal", return_value=mock_result):
        result = runner.invoke(app, ["signal", "cn-stock", "000001.SZ", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["symbol"] == "000001.SZ"
    assert data["pe_ratio"] is None
    assert data["limit_up_hit"] is True
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "cli_cn_stock" -v
```
预期：`No such command 'cn-stock'`

- [ ] **Step 3: 在 cli.py 中添加 cn-stock 命令**

在 `src/hiveflow/cli.py` 文件顶部的 import 区域，找到其他 application 导入，追加：

```python
from hiveflow.application.cn_signals import build_cn_stock_signal, build_cn_market_signal
```

然后找到 `signal_app` 命令组中已有命令（如 `snapshot` 命令）之后，追加：

```python
@signal_app.command("cn-stock")
def signal_cn_stock_command(
    symbol: str = typer.Argument(..., help="A 股 symbol，如 000001.SZ"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """获取个股 A 股特有信号（PE/PB、涨跌停触发）。

    数据来源：腾讯行情（主）+ akshare（回退/补充）。
    涨跌停检测仅覆盖主板非 ST 股 ±10%。
    """
    app_settings = Settings()
    result = build_cn_stock_signal(symbol.upper(), settings=app_settings)

    if output == "json":
        import json
        data = {
            "symbol": result.symbol,
            "date": result.date,
            "market": result.market,
            "pe_ratio": result.pe_ratio,
            "pb_ratio": result.pb_ratio,
            "limit_up_hit": result.limit_up_hit,
            "limit_down_hit": result.limit_down_hit,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        }
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        def _fmt(v) -> str:
            return "N/A" if v is None else str(v)

        typer.echo(f"symbol        : {result.symbol}")
        typer.echo(f"date          : {result.date}")
        typer.echo(f"pe_ratio      : {_fmt(result.pe_ratio)}")
        typer.echo(f"pb_ratio      : {_fmt(result.pb_ratio)}")
        typer.echo(f"limit_up_hit  : {_fmt(result.limit_up_hit)}")
        typer.echo(f"limit_down_hit: {_fmt(result.limit_down_hit)}")
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run pytest tests/test_cn_signals.py -k "cli_cn_stock" -v
```
预期：`2 passed`

- [ ] **Step 5: 提交**

```bash
git add src/hiveflow/cli.py tests/test_cn_signals.py
git commit -m "feat: CLI signal cn-stock 命令"
```

---

### Task 8: signal cn-market 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cn_signals.py`（追加）

- [ ] **Step 1: 追加测试**

```python
def test_cli_cn_market_text_output(tmp_path) -> None:
    """signal cn-market 文本输出结构正确。"""
    from typer.testing import CliRunner
    from unittest.mock import patch
    from hiveflow.cli import app
    import datetime as dt

    runner = CliRunner()
    ts = dt.datetime(2026, 3, 24, 7, 30, tzinfo=dt.timezone.utc)

    from hiveflow.domain.cn_signals import CNMarketSignal
    mock_result = CNMarketSignal(
        id=1, date="2026-03-24", timestamp=ts,
        northbound_net_flow=32.5, margin_balance=14832.6,
        limit_up_count=43, limit_down_count=12,
    )

    with patch("hiveflow.cli.build_cn_market_signal", return_value=mock_result):
        result = runner.invoke(app, ["signal", "cn-market"])

    assert result.exit_code == 0
    assert "32.5" in result.output
    assert "43" in result.output


def test_cli_cn_market_json_output(tmp_path) -> None:
    """signal cn-market --output json 输出合法 JSON，None 字段为 null。"""
    import json
    from typer.testing import CliRunner
    from unittest.mock import patch
    from hiveflow.cli import app
    import datetime as dt

    runner = CliRunner()
    ts = dt.datetime(2026, 3, 24, 7, 30, tzinfo=dt.timezone.utc)

    from hiveflow.domain.cn_signals import CNMarketSignal
    mock_result = CNMarketSignal(
        id=1, date="2026-03-24", timestamp=ts,
        northbound_net_flow=None, margin_balance=None,
        limit_up_count=None, limit_down_count=None,
    )

    with patch("hiveflow.cli.build_cn_market_signal", return_value=mock_result):
        result = runner.invoke(app, ["signal", "cn-market", "--output", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["northbound_net_flow"] is None
    assert data["date"] == "2026-03-24"
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run pytest tests/test_cn_signals.py -k "cli_cn_market" -v
```
预期：`No such command 'cn-market'`

- [ ] **Step 3: 在 cli.py 中添加 cn-market 命令**

在 `signal cn-stock` 命令之后追加：

```python
@signal_app.command("cn-market")
def signal_cn_market_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """获取市场级 A 股信号（北向资金、融资余额、全市场涨跌停家数）。

    数据单位：northbound_net_flow / margin_balance 为亿元。
    数据来源：akshare（无腾讯回退）；任一字段获取失败时显示 N/A。
    """
    app_settings = Settings()
    result = build_cn_market_signal(settings=app_settings)

    if output == "json":
        import json
        data = {
            "date": result.date,
            "northbound_net_flow": result.northbound_net_flow,
            "margin_balance": result.margin_balance,
            "limit_up_count": result.limit_up_count,
            "limit_down_count": result.limit_down_count,
            "timestamp": result.timestamp.isoformat() if result.timestamp else None,
        }
        typer.echo(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        def _fmt(v) -> str:
            return "N/A" if v is None else str(v)

        typer.echo(f"date               : {result.date}")
        typer.echo(f"northbound_net_flow: {_fmt(result.northbound_net_flow)}")
        typer.echo(f"margin_balance     : {_fmt(result.margin_balance)}")
        typer.echo(f"limit_up_count     : {_fmt(result.limit_up_count)}")
        typer.echo(f"limit_down_count   : {_fmt(result.limit_down_count)}")
```

- [ ] **Step 4: 运行全部新增测试**

```bash
uv run pytest tests/test_cn_signals.py -v
```
预期：全部 passed（约 21 个测试）

- [ ] **Step 5: 全量回归**

```bash
uv run pytest -q
```
预期：全部 passed，390+ 基线不退步。

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/cli.py tests/test_cn_signals.py
git commit -m "feat: CLI signal cn-market 命令，Phase 2-A 完成"
```

---

## 验证端到端

```bash
# 1. 全量测试
uv run pytest -q

# 2. 文本输出（需要网络 + akshare）
uv run hiveflow signal cn-stock 000001.SZ
uv run hiveflow signal cn-market

# 3. JSON 输出
uv run hiveflow signal cn-stock 000001.SZ --output json
uv run hiveflow signal cn-market --output json

# 4. 帮助文档
uv run hiveflow signal --help
```

预期：无 exception，网络失败的字段显示 N/A（文本）或 null（JSON）。
