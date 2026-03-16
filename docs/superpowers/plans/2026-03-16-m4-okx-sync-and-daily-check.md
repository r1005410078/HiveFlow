# M4 OKX 接入 + 每日健康检查 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `hiveflow sync`（从 OKX 拉取持仓和价格）与 `hiveflow check`（输出风险信号和结论），让用户每天两条命令完成持仓健康检查。

**Architecture:** OKX HTTP 客户端放于基础设施层（`infrastructure/okx/okx_provider.py`），不含业务逻辑；应用层 `sync.py` 编排数据写入，`health_check.py` 计算风险指标并生成结论；风险计算（最大回撤）新增至 `services/risk_engine.py`；CLI 新增 `sync` 和 `check` 两个顶层命令。

**Tech Stack:** Python 3.12+, typer, SQLModel, SQLite, urllib.request（标准库，无需新依赖）, pydantic-settings, rich, pytest

---

## Chunk 1: OKX 基础设施层

### Task 1: 扩展 config 以支持 OKX API Key

**Files:**
- Modify: `src/hiveflow/config.py`
- Test: `tests/test_config_okx.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_config_okx.py
import os
from hiveflow.config import Settings


def test_okx_settings_default_to_none() -> None:
    s = Settings()
    assert s.okx_api_key is None
    assert s.okx_api_secret is None
    assert s.okx_api_passphrase is None


def test_okx_settings_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("OKX_API_KEY", "key123")
    monkeypatch.setenv("OKX_API_SECRET", "secret456")
    monkeypatch.setenv("OKX_API_PASSPHRASE", "pass789")
    s = Settings()
    assert s.okx_api_key == "key123"
    assert s.okx_api_secret == "secret456"
    assert s.okx_api_passphrase == "pass789"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_config_okx.py -v
```
Expected: FAIL — `Settings` 没有 `okx_api_key` 字段

- [ ] **Step 3: 修改 config.py**

```python
# src/hiveflow/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    database_url: str = f"sqlite:///{Path.cwd() / 'data' / 'hiveflow.db'}"
    target_template_file: str = str(Path.cwd() / "config" / "target-templates.json")

    # OKX API 配置（可选，不设置则 sync 命令不可用）
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_api_passphrase: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="",          # OKX_ 前缀直接读取，不加 HIVEFLOW_ 前缀
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
```

注意：`env_prefix=""` 让 `OKX_API_KEY` 直接映射到 `okx_api_key`，不会影响现有 `HIVEFLOW_DATABASE_URL` 等变量（pydantic-settings 对每个字段单独处理前缀时，需要用 `model_validator` 或分拆 Settings 类）。

实际上更简单的做法是保留 `HIVEFLOW_` 前缀，改为读 `HIVEFLOW_OKX_API_KEY`：

```python
# src/hiveflow/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置。"""

    database_url: str = f"sqlite:///{Path.cwd() / 'data' / 'hiveflow.db'}"
    target_template_file: str = str(Path.cwd() / "config" / "target-templates.json")

    # OKX API 配置（env: OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE）
    okx_api_key: str | None = None
    okx_api_secret: str | None = None
    okx_api_passphrase: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="HIVEFLOW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
```

同步更新测试使用 `HIVEFLOW_OKX_API_KEY`：

```python
def test_okx_settings_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "key123")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "secret456")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "pass789")
    s = Settings()
    assert s.okx_api_key == "key123"
    assert s.okx_api_secret == "secret456"
    assert s.okx_api_passphrase == "pass789"
```

- [ ] **Step 4: 运行确认通过**

```bash
uv run python -m pytest tests/test_config_okx.py -v
```
Expected: 2 passed

- [ ] **Step 5: 全量测试确认不破坏现有功能**

```bash
uv run python -m pytest -q
```
Expected: 89 passed（87 原有 + 2 新增）

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/config.py tests/test_config_okx.py
git commit -m "feat: config 新增 OKX API Key 设置项"
```

---

### Task 2: OKX Provider — 持仓和价格拉取

**Files:**
- Create: `src/hiveflow/infrastructure/okx/__init__.py`
- Create: `src/hiveflow/infrastructure/okx/okx_provider.py`
- Test: `tests/test_okx_provider.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_okx_provider.py
"""OKX provider 单元测试——所有网络请求均 mock。"""
import json
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError,
    OkxProvider,
    OkxRateLimitError,
    OkxTimeoutError,
    OkxPosition,
    OkxCandle,
)


def _make_response(body: dict, status: int = 200) -> MagicMock:
    """构造 mock HTTP 响应。"""
    resp = MagicMock()
    resp.status = status
    resp.read.return_value = json.dumps(body).encode()
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


# ── 持仓 ──────────────────────────────────────────────────────────────────────

def test_fetch_positions_returns_spot_holdings() -> None:
    """返回现货持仓并规范化 symbol。"""
    payload = {
        "code": "0",
        "data": [
            {"instId": "BTC-USDT", "instType": "SPOT", "availEq": "0.5", "upl": "0", "notionalUsd": "20000"},
            {"instId": "ETH-USDT", "instType": "SPOT", "availEq": "3.0", "upl": "0", "notionalUsd": "9000"},
            {"instId": "BTC-USDT-SWAP", "instType": "SWAP", "availEq": "1", "upl": "0", "notionalUsd": "40000"},
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        provider = OkxProvider(api_key="k", api_secret="s", passphrase="p")
        positions = provider.fetch_positions()

    assert len(positions) == 2  # SWAP 被过滤
    assert positions[0].symbol == "BTC"
    assert positions[0].quantity == 0.5
    assert positions[0].market_value_usdt == 20000.0
    assert positions[1].symbol == "ETH"


def test_fetch_positions_raises_on_401() -> None:
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as mock_open:
        mock_open.side_effect = Exception("HTTP Error 401")
        provider = OkxProvider(api_key="bad", api_secret="bad", passphrase="bad")
        with pytest.raises(OkxAuthError):
            provider.fetch_positions()


def test_fetch_positions_raises_on_timeout() -> None:
    import socket
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as mock_open:
        mock_open.side_effect = TimeoutError()
        provider = OkxProvider(api_key="k", api_secret="s", passphrase="p")
        with pytest.raises(OkxTimeoutError):
            provider.fetch_positions()


def test_fetch_positions_raises_on_rate_limit() -> None:
    payload = {"code": "50011", "msg": "Too Many Requests", "data": []}
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        provider = OkxProvider(api_key="k", api_secret="s", passphrase="p")
        with pytest.raises(OkxRateLimitError):
            provider.fetch_positions()


# ── K 线 ──────────────────────────────────────────────────────────────────────

def test_fetch_candles_returns_daily_bars() -> None:
    """返回日线 K 线并规范化字段。"""
    # OKX candles 返回 [ts, o, h, l, c, vol, ...]，ts 为毫秒字符串
    payload = {
        "code": "0",
        "data": [
            ["1710288000000", "70000", "71000", "69000", "70500", "100", "100"],
            ["1710201600000", "68000", "70000", "67000", "70000", "90", "90"],
        ],
    }
    with patch("hiveflow.infrastructure.okx.okx_provider.urllib.request.urlopen") as mock_open:
        mock_open.return_value = _make_response(payload)
        provider = OkxProvider(api_key="k", api_secret="s", passphrase="p")
        candles = provider.fetch_candles("BTC-USDT", days=2)

    assert len(candles) == 2
    assert candles[0].symbol == "BTC"
    assert candles[0].open == 70000.0
    assert candles[0].close == 70500.0
    assert candles[0].timestamp.year == 2024
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_okx_provider.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: 创建 `__init__.py`**

```python
# src/hiveflow/infrastructure/okx/__init__.py
```
（空文件）

- [ ] **Step 4: 实现 `okx_provider.py`**

```python
# src/hiveflow/infrastructure/okx/okx_provider.py
"""OKX REST API 客户端——纯数据拉取，无业务逻辑。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


BASE_URL = "https://www.okx.com"
TIMEOUT_SECONDS = 10


# ── 自定义异常 ────────────────────────────────────────────────────────────────

class OkxAuthError(Exception):
    """API 鉴权失败（401 或签名错误）。"""


class OkxTimeoutError(Exception):
    """网络超时。"""


class OkxRateLimitError(Exception):
    """请求频率超限（429 或 code=50011）。"""


# ── 数据结构 ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class OkxPosition:
    symbol: str               # 规范化后，如 BTC（截取 BTC-USDT 的连字符前部分）
    quantity: float
    market_value_usdt: float  # 以 USDT 计价的市值


@dataclass(frozen=True)
class OkxCandle:
    symbol: str
    timestamp: datetime       # UTC
    open: float
    high: float
    low: float
    close: float
    volume: float


# ── Provider ──────────────────────────────────────────────────────────────────

class OkxProvider:
    """OKX API 数据拉取器。"""

    def __init__(self, api_key: str, api_secret: str, passphrase: str) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._passphrase = passphrase

    # ── 公开方法 ──────────────────────────────────────────────────────────────

    def fetch_positions(self) -> list[OkxPosition]:
        """拉取现货持仓，过滤衍生品。"""
        data = self._get_authenticated("/api/v5/account/balance")
        positions = []
        # balance 接口返回格式: data[0]["details"] 列表
        details = data[0].get("details", []) if data else []
        for item in details:
            ccy = item.get("ccy", "").upper()
            eq = float(item.get("eq") or 0)
            usdt_val = float(item.get("eqUsd") or 0)
            if eq <= 0:
                continue
            positions.append(OkxPosition(
                symbol=ccy,
                quantity=eq,
                market_value_usdt=usdt_val,
            ))
        return positions

    def fetch_candles(self, inst_id: str, days: int) -> list[OkxCandle]:
        """拉取日线 K 线，days 为回溯天数（最大 365）。"""
        symbol = inst_id.split("-")[0].upper()
        limit = min(days, 100)  # OKX 单次最多 100 根
        path = f"/api/v5/market/candles?instId={inst_id}&bar=1D&limit={limit}"
        data = self._get_public(path)
        candles = []
        for row in data:
            ts_ms = int(row[0])
            ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
            candles.append(OkxCandle(
                symbol=symbol,
                timestamp=ts,
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            ))
        return candles

    # ── 私有工具 ──────────────────────────────────────────────────────────────

    def _get_authenticated(self, path: str) -> list:
        """带签名的 GET 请求。"""
        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        sign = self._sign("GET", path, ts, "")
        headers = {
            "OK-ACCESS-KEY": self._api_key,
            "OK-ACCESS-SIGN": sign,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": self._passphrase,
            "Content-Type": "application/json",
        }
        return self._request(path, headers)

    def _get_public(self, path: str) -> list:
        """无鉴权的公开 GET 请求。"""
        return self._request(path, {})

    def _sign(self, method: str, path: str, timestamp: str, body: str) -> str:
        message = f"{timestamp}{method}{path}{body}"
        mac = hmac.new(
            self._api_secret.encode(),
            message.encode(),
            hashlib.sha256,
        )
        return base64.b64encode(mac.digest()).decode()

    def _request(self, path: str, headers: dict) -> list:
        url = BASE_URL + path
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
                body = json.loads(resp.read())
        except TimeoutError:
            raise OkxTimeoutError("网络超时，请稍后重试。")
        except Exception as e:
            msg = str(e)
            if "401" in msg:
                raise OkxAuthError(
                    "OKX API 鉴权失败（401）。请检查 .env 中的配置。"
                )
            raise OkxTimeoutError(f"网络请求失败：{msg}")

        code = body.get("code", "0")
        if code == "50011":
            raise OkxRateLimitError("请求频率超限（429），请稍后重试。")
        if code != "0":
            raise OkxAuthError(f"OKX API 返回错误 code={code}：{body.get('msg')}")

        return body.get("data", [])
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_okx_provider.py -v
```
Expected: 6 passed

- [ ] **Step 6: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 95 passed

- [ ] **Step 7: 提交**

```bash
git add src/hiveflow/infrastructure/okx/ tests/test_okx_provider.py
git commit -m "feat: 新增 OKX 基础设施层（持仓、K线拉取）"
```

---

## Chunk 2: Sync 用例 + CLI 命令

### Task 3: Sync 应用层用例

**Files:**
- Create: `src/hiveflow/application/sync.py`
- Test: `tests/test_sync.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_sync.py
"""sync 用例集成测试——mock OKX provider，真实写入临时数据库。"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from hiveflow.application.sync import SyncResult, sync_from_okx
from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError,
    OkxCandle,
    OkxPosition,
)


def _settings(tmp_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path}/sync.db",
        okx_api_key="k",
        okx_api_secret="s",
        okx_api_passphrase="p",
    )


def _make_provider(positions=None, candles=None) -> MagicMock:
    provider = MagicMock()
    provider.fetch_positions.return_value = positions or []
    provider.fetch_candles.return_value = candles or []
    return provider


def test_sync_writes_positions_to_db(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    okx_positions = [
        OkxPosition(symbol="BTC", quantity=0.5, market_value_usdt=20000.0),
        OkxPosition(symbol="ETH", quantity=3.0, market_value_usdt=9000.0),
    ]
    provider = _make_provider(positions=okx_positions)

    result = sync_from_okx(provider=provider, settings=settings)

    assert result.positions_synced == 2
    assert result.candles_synced == 0
    with get_session(settings) as session:
        rows = session.exec(__import__("sqlmodel").select(Position)).all()
    assert len(rows) == 2
    symbols = {r.symbol for r in rows}
    assert symbols == {"BTC", "ETH"}
    # 权重应被计算：BTC = 20000/29000
    btc = next(r for r in rows if r.symbol == "BTC")
    assert abs(btc.weight - 20000 / 29000) < 0.001


def test_sync_writes_candles_to_db(tmp_path) -> None:
    settings = _settings(tmp_path)
    create_all_tables(settings)
    ts = datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
    okx_candles = [
        OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70500, volume=100),
    ]
    provider = _make_provider(candles=okx_candles)

    result = sync_from_okx(provider=provider, settings=settings, days=7)

    assert result.candles_synced == 1
    with get_session(settings) as session:
        rows = session.exec(__import__("sqlmodel").select(MarketBar)).all()
    assert len(rows) == 1
    assert rows[0].symbol == "BTC"
    assert rows[0].close == 70500.0


def test_sync_is_atomic_on_provider_error(tmp_path) -> None:
    """provider 抛出异常时，不写入任何数据。"""
    settings = _settings(tmp_path)
    create_all_tables(settings)
    provider = MagicMock()
    provider.fetch_positions.side_effect = OkxAuthError("鉴权失败")

    with pytest.raises(OkxAuthError):
        sync_from_okx(provider=provider, settings=settings)

    with get_session(settings) as session:
        pos_rows = session.exec(__import__("sqlmodel").select(Position)).all()
    assert len(pos_rows) == 0


def test_sync_upserts_candles_by_symbol_and_timestamp(tmp_path) -> None:
    """相同 (symbol, timestamp) 的 K 线覆盖写入，不产生重复行。"""
    settings = _settings(tmp_path)
    create_all_tables(settings)
    ts = datetime(2026, 3, 15, 0, 0, 0, tzinfo=timezone.utc)
    candle_v1 = OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70000, volume=100)
    candle_v2 = OkxCandle(symbol="BTC", timestamp=ts, open=70000, high=71000, low=69000, close=70999, volume=200)

    sync_from_okx(provider=_make_provider(candles=[candle_v1]), settings=settings, days=1)
    sync_from_okx(provider=_make_provider(candles=[candle_v2]), settings=settings, days=1)

    with get_session(settings) as session:
        rows = session.exec(__import__("sqlmodel").select(MarketBar)).all()
    assert len(rows) == 1
    assert rows[0].close == 70999.0
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_sync.py -v
```
Expected: FAIL — `sync_from_okx` not found

- [ ] **Step 3: 实现 `sync.py`**

```python
# src/hiveflow/application/sync.py
"""OKX 数据同步用例。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlmodel import delete, select

from hiveflow.config import Settings
from hiveflow.db import create_all_tables, get_session
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.infrastructure.okx.okx_provider import OkxProvider


@dataclass(frozen=True)
class SyncResult:
    """同步结果摘要。"""

    synced_at: datetime
    positions_synced: int
    candles_synced: int
    total_value_usdt: float

    def to_dict(self) -> dict:
        return {
            "synced_at": self.synced_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "positions_synced": self.positions_synced,
            "candles_synced": self.candles_synced,
            "total_value_usdt": round(self.total_value_usdt, 2),
        }


def sync_from_okx(
    provider: OkxProvider,
    settings: Settings | None = None,
    days: int | None = None,
) -> SyncResult:
    """从 OKX 拉取数据并写入数据库。全成功或全失败（原子性）。"""
    app_settings = settings or Settings()
    create_all_tables(app_settings)

    # 1. 先拉取所有数据（任何一步失败都会在写入前抛出异常）
    okx_positions = provider.fetch_positions()
    okx_candles = []
    if days is not None:
        symbols = list({p.symbol for p in okx_positions})
        for symbol in symbols:
            inst_id = f"{symbol}-USDT"
            okx_candles.extend(provider.fetch_candles(inst_id, days=days))

    # 2. 全部拉取成功后，单事务写入
    total_value = sum(p.market_value_usdt for p in okx_positions)

    with get_session(app_settings) as session:
        # 持仓：全量替换（当前持仓是最新快照）
        session.exec(delete(Position))
        for p in okx_positions:
            weight = p.market_value_usdt / total_value if total_value > 0 else 0.0
            session.add(Position(
                symbol=p.symbol,
                quantity=p.quantity,
                market_value=p.market_value_usdt,
                weight=weight,
            ))

        # K 线：按 (symbol, timestamp) upsert
        for c in okx_candles:
            session.exec(
                delete(MarketBar).where(
                    (MarketBar.symbol == c.symbol) & (MarketBar.timestamp == c.timestamp)
                )
            )
            session.add(MarketBar(
                symbol=c.symbol,
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            ))

        session.commit()

    return SyncResult(
        synced_at=datetime.now(tz=timezone.utc),
        positions_synced=len(okx_positions),
        candles_synced=len(okx_candles),
        total_value_usdt=total_value,
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_sync.py -v
```
Expected: 4 passed

- [ ] **Step 5: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 101 passed

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/application/sync.py tests/test_sync.py
git commit -m "feat: 新增 OKX 数据同步用例（sync_from_okx）"
```

---

### Task 4: Sync CLI 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cli_sync.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli_sync.py
"""sync CLI 命令测试——mock OkxProvider。"""
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from hiveflow.cli import app
from hiveflow.application.sync import SyncResult
from hiveflow.infrastructure.okx.okx_provider import OkxAuthError, OkxTimeoutError


def _mock_sync_result() -> SyncResult:
    return SyncResult(
        synced_at=datetime(2026, 3, 16, 9, 32, 0, tzinfo=timezone.utc),
        positions_synced=3,
        candles_synced=0,
        total_value_usdt=12450.0,
    )


def test_sync_command_exists() -> None:
    result = CliRunner().invoke(app, ["sync", "--help"])
    assert result.exit_code == 0


def test_sync_outputs_summary(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.sync_from_okx", return_value=_mock_sync_result()):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 0
    assert "同步完成" in result.output
    assert "3" in result.output  # positions_synced


def test_sync_json_output(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    with patch("hiveflow.cli.sync_from_okx", return_value=_mock_sync_result()):
        result = CliRunner().invoke(app, ["sync", "--output", "json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["positions_synced"] == 3


def test_sync_fails_gracefully_without_api_key() -> None:
    """未配置 API Key 时输出友好错误，退出码 1。"""
    result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "OKX_API_KEY" in result.output


def test_sync_with_days_flag(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "k")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "s")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "p")
    mock_result = SyncResult(
        synced_at=datetime(2026, 3, 16, 9, 32, 0, tzinfo=timezone.utc),
        positions_synced=3,
        candles_synced=21,
        total_value_usdt=12450.0,
    )
    with patch("hiveflow.cli.sync_from_okx", return_value=mock_result) as mock_fn:
        result = CliRunner().invoke(app, ["sync", "--days", "7"])
    assert result.exit_code == 0
    # 确认 days=7 被传入用例
    call_kwargs = mock_fn.call_args.kwargs
    assert call_kwargs.get("days") == 7


def test_sync_shows_error_on_auth_failure(monkeypatch) -> None:
    monkeypatch.setenv("HIVEFLOW_OKX_API_KEY", "bad")
    monkeypatch.setenv("HIVEFLOW_OKX_API_SECRET", "bad")
    monkeypatch.setenv("HIVEFLOW_OKX_API_PASSPHRASE", "bad")
    with patch("hiveflow.cli.sync_from_okx", side_effect=OkxAuthError("鉴权失败")):
        result = CliRunner().invoke(app, ["sync"])
    assert result.exit_code == 1
    assert "鉴权失败" in result.output
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_cli_sync.py -v
```
Expected: FAIL — `sync` 命令不存在

- [ ] **Step 3: 在 cli.py 中添加 `sync` 命令**

在 cli.py 顶部 import 区新增：

```python
from hiveflow.application.sync import SyncResult, sync_from_okx
from hiveflow.infrastructure.okx.okx_provider import (
    OkxAuthError,
    OkxProvider,
    OkxRateLimitError,
    OkxTimeoutError,
)
```

在 cli.py 底部（`run` 函数之前）新增：

```python
@app.command()
def sync(
    days: int | None = typer.Option(None, "--days", help="同步最近 N 天 K 线（最大 365）"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """从 OKX 拉取最新持仓和价格，写入本地数据库。"""
    settings = Settings()

    # 检查 API Key 是否配置
    if not settings.okx_api_key or not settings.okx_api_secret or not settings.okx_api_passphrase:
        console.print(
            "错误：未配置 OKX API Key。请在 .env 文件中设置：\n"
            "  HIVEFLOW_OKX_API_KEY=xxx\n"
            "  HIVEFLOW_OKX_API_SECRET=xxx\n"
            "  HIVEFLOW_OKX_API_PASSPHRASE=xxx",
            style="bold red",
        )
        raise typer.Exit(code=1)

    if days is not None and not (1 <= days <= 365):
        console.print("错误：--days 必须在 1 到 365 之间。", style="bold red")
        raise typer.Exit(code=1)

    provider = OkxProvider(
        api_key=settings.okx_api_key,
        api_secret=settings.okx_api_secret,
        passphrase=settings.okx_api_passphrase,
    )

    try:
        result = sync_from_okx(provider=provider, settings=settings, days=days)
    except (OkxAuthError, OkxTimeoutError, OkxRateLimitError) as e:
        console.print(f"错误：{e}", style="bold red")
        raise typer.Exit(code=1)

    if output == "json":
        console.print(json.dumps(result.to_dict(), ensure_ascii=False))
        return

    console.print(f"[bold green]同步完成[/bold green]  {result.synced_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    console.print(f"持仓：{result.positions_synced} 个币种  总估值：{result.total_value_usdt:,.2f} USDT")
    if result.candles_synced > 0:
        console.print(f"K 线：{result.candles_synced} 条记录已写入")
```

同时在文件顶部 import 区添加：
```python
from hiveflow.config import Settings
```
（若已存在则跳过）

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_cli_sync.py -v
```
Expected: 6 passed

- [ ] **Step 5: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 107 passed

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/cli.py tests/test_cli_sync.py
git commit -m "feat: 新增 sync CLI 命令（hiveflow sync）"
```

---

## Chunk 3: 风险引擎 + 健康检查 + CLI

### Task 5: 最大回撤计算

**Files:**
- Modify: `src/hiveflow/services/risk_engine.py`
- Test: `tests/test_drawdown.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_drawdown.py
"""最大回撤计算单元测试。"""
from datetime import datetime, timezone

import pytest

from hiveflow.domain.market_data import MarketBar
from hiveflow.services.risk_engine import calculate_max_drawdown


def _bar(day: int, close: float) -> MarketBar:
    return MarketBar(
        symbol="BTC",
        timestamp=datetime(2026, 3, day, tzinfo=timezone.utc),
        open=close,
        high=close,
        low=close,
        close=close,
        volume=1000.0,
    )


def test_max_drawdown_monotone_up() -> None:
    """单调上涨时回撤为 0。"""
    bars = [_bar(i, float(i * 1000)) for i in range(1, 8)]
    assert calculate_max_drawdown(bars) == 0.0


def test_max_drawdown_simple_drop() -> None:
    """从 100 跌到 80，回撤 -20%。"""
    bars = [_bar(1, 100.0), _bar(2, 90.0), _bar(3, 80.0)]
    result = calculate_max_drawdown(bars)
    assert abs(result - (-0.20)) < 0.001


def test_max_drawdown_recovery() -> None:
    """跌后回升，仍取最大回撤。"""
    bars = [_bar(1, 100.0), _bar(2, 60.0), _bar(3, 90.0)]
    result = calculate_max_drawdown(bars)
    assert abs(result - (-0.40)) < 0.001


def test_max_drawdown_empty_returns_zero() -> None:
    assert calculate_max_drawdown([]) == 0.0


def test_max_drawdown_single_bar_returns_zero() -> None:
    assert calculate_max_drawdown([_bar(1, 100.0)]) == 0.0
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_drawdown.py -v
```
Expected: FAIL — `calculate_max_drawdown` not found

- [ ] **Step 3: 在 risk_engine.py 中添加回撤计算**

```python
# 在 src/hiveflow/services/risk_engine.py 末尾追加：

from hiveflow.domain.market_data import MarketBar


def calculate_max_drawdown(bars: list[MarketBar]) -> float:
    """计算给定 K 线序列的最大回撤（负数或 0）。

    定义：以窗口内历史最高收盘价为基准，计算至最低点的跌幅。
    返回值：0.0（无回撤）到 -1.0（跌至 0）之间的浮点数。
    """
    if len(bars) < 2:
        return 0.0

    closes = [b.close for b in bars]
    max_drawdown = 0.0
    peak = closes[0]

    for close in closes[1:]:
        if close > peak:
            peak = close
        drawdown = (close - peak) / peak
        if drawdown < max_drawdown:
            max_drawdown = drawdown

    return max_drawdown
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_drawdown.py -v
```
Expected: 5 passed

- [ ] **Step 5: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 112 passed

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/services/risk_engine.py tests/test_drawdown.py
git commit -m "feat: risk_engine 新增最大回撤计算函数"
```

---

### Task 6: 健康检查用例

**Files:**
- Create: `src/hiveflow/application/health_check.py`
- Test: `tests/test_health_check.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_health_check.py
"""健康检查用例单元测试。"""
from datetime import datetime, timezone

from hiveflow.application.health_check import (
    AlertLevel,
    AssetRiskSignal,
    HealthCheckResult,
    run_health_check,
)
from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position


def _pos(symbol: str, weight: float) -> Position:
    return Position(symbol=symbol, quantity=1.0, market_value=weight * 10000, weight=weight)


def _bars(symbol: str, closes: list[float]) -> list[MarketBar]:
    return [
        MarketBar(
            symbol=symbol,
            timestamp=datetime(2026, 3, i + 1, tzinfo=timezone.utc),
            open=c, high=c, low=c, close=c, volume=1000.0,
        )
        for i, c in enumerate(closes)
    ]


def test_all_normal_gives_safe_verdict() -> None:
    positions = [_pos("BTC", 1.0)]
    bars_by_symbol = {"BTC": _bars("BTC", [100, 102, 101, 103, 104, 105, 106])}
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)
    assert result.verdict == "safe"
    assert result.signals[0].alert_level == AlertLevel.NORMAL


def test_drawdown_warning_triggers_watch_verdict() -> None:
    positions = [_pos("ETH", 1.0)]
    bars_by_symbol = {"ETH": _bars("ETH", [100, 95, 90, 85, 87, 88, 89])}
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)
    assert result.verdict == "watch"
    assert result.signals[0].alert_level == AlertLevel.WARNING


def test_severe_drawdown_triggers_danger_verdict() -> None:
    positions = [_pos("SOL", 1.0)]
    bars_by_symbol = {"SOL": _bars("SOL", [100, 80, 75, 72, 70, 69, 68])}
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)
    assert result.verdict == "danger"
    assert result.signals[0].alert_level == AlertLevel.DANGER


def test_no_bars_skips_risk_layer() -> None:
    positions = [_pos("BTC", 1.0)]
    result = run_health_check(positions=positions, bars_by_symbol={})
    assert result.signals == []
    assert result.has_no_history is True
    assert result.verdict == "safe"  # 无数据时不告警


def test_multiple_symbols_mixed_levels() -> None:
    positions = [_pos("BTC", 0.5), _pos("ETH", 0.5)]
    bars_by_symbol = {
        "BTC": _bars("BTC", [100, 102, 101, 103, 104, 105, 106]),  # 正常
        "ETH": _bars("ETH", [100, 80, 75, 72, 70, 69, 68]),         # 危险
    }
    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)
    assert result.verdict == "danger"
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_health_check.py -v
```
Expected: FAIL — module not found

- [ ] **Step 3: 实现 `health_check.py`**

```python
# src/hiveflow/application/health_check.py
"""每日持仓健康检查用例。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from hiveflow.domain.market_data import MarketBar
from hiveflow.domain.positions import Position
from hiveflow.services.risk_engine import calculate_max_drawdown


# 回撤告警阈值
WARNING_DRAWDOWN = -0.10   # -10%
DANGER_DRAWDOWN = -0.20    # -20%


class AlertLevel(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"
    DANGER = "danger"


@dataclass(frozen=True)
class AssetRiskSignal:
    symbol: str
    max_drawdown_7d: float        # 负数或 0
    alert_level: AlertLevel
    action_hint: str              # 建议动作文字


@dataclass
class HealthCheckResult:
    signals: list[AssetRiskSignal] = field(default_factory=list)
    has_no_history: bool = False  # 无历史行情数据时为 True

    @property
    def verdict(self) -> str:
        """safe / watch / danger"""
        if any(s.alert_level == AlertLevel.DANGER for s in self.signals):
            return "danger"
        if any(s.alert_level == AlertLevel.WARNING for s in self.signals):
            return "watch"
        return "safe"

    @property
    def verdict_summary(self) -> str:
        """一句话结论文字。"""
        if self.verdict == "safe":
            return "今天安全，无需操作"
        danger_symbols = [s.symbol for s in self.signals if s.alert_level == AlertLevel.DANGER]
        warning_symbols = [s.symbol for s in self.signals if s.alert_level == AlertLevel.WARNING]
        flagged = danger_symbols or warning_symbols
        symbols_str = "、".join(flagged)
        if self.verdict == "danger":
            return f"危险，建议处理 — {symbols_str} 回撤超过 20%"
        return f"建议关注 — {symbols_str} 近7日回撤较大"


def run_health_check(
    positions: list[Position],
    bars_by_symbol: dict[str, list[MarketBar]],
) -> HealthCheckResult:
    """计算各持仓币种的风险信号，生成健康检查结论。"""
    result = HealthCheckResult()

    if not bars_by_symbol:
        result.has_no_history = True
        return result

    for pos in positions:
        bars = bars_by_symbol.get(pos.symbol, [])
        if not bars:
            continue

        # 只取最近 7 根日线
        recent_bars = sorted(bars, key=lambda b: b.timestamp)[-7:]
        drawdown = calculate_max_drawdown(recent_bars)
        level, hint = _classify(pos.symbol, drawdown)
        result.signals.append(AssetRiskSignal(
            symbol=pos.symbol,
            max_drawdown_7d=drawdown,
            alert_level=level,
            action_hint=hint,
        ))

    return result


def _classify(symbol: str, drawdown: float) -> tuple[AlertLevel, str]:
    if drawdown <= DANGER_DRAWDOWN:
        return AlertLevel.DANGER, f"{symbol} 回撤超过 20%，建议评估是否止损"
    if drawdown <= WARNING_DRAWDOWN:
        return AlertLevel.WARNING, f"{symbol} 回撤偏大，留意是否触发止损线"
    return AlertLevel.NORMAL, ""
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_health_check.py -v
```
Expected: 6 passed

- [ ] **Step 5: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 118 passed

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/application/health_check.py tests/test_health_check.py
git commit -m "feat: 新增健康检查用例（run_health_check）"
```

---

### Task 7: Check CLI 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cli_check.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli_check.py
"""check CLI 命令测试。"""
from unittest.mock import patch

from typer.testing import CliRunner

from hiveflow.application.health_check import (
    AlertLevel,
    AssetRiskSignal,
    HealthCheckResult,
)
from hiveflow.cli import app


def _safe_result() -> HealthCheckResult:
    r = HealthCheckResult()
    r.signals = [AssetRiskSignal(symbol="BTC", max_drawdown_7d=-0.03, alert_level=AlertLevel.NORMAL, action_hint="")]
    return r


def _danger_result() -> HealthCheckResult:
    r = HealthCheckResult()
    r.signals = [AssetRiskSignal(symbol="ETH", max_drawdown_7d=-0.25, alert_level=AlertLevel.DANGER, action_hint="ETH 回撤超过 20%，建议评估是否止损")]
    return r


def _no_history_result() -> HealthCheckResult:
    r = HealthCheckResult()
    r.has_no_history = True
    return r


def test_check_command_exists() -> None:
    result = CliRunner().invoke(app, ["check", "--help"])
    assert result.exit_code == 0


def test_check_outputs_safe_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/check.db")
    with patch("hiveflow.cli.run_health_check", return_value=_safe_result()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "安全" in result.output


def test_check_outputs_danger_verdict(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/check.db")
    with patch("hiveflow.cli.run_health_check", return_value=_danger_result()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0  # check 始终退出码 0
    assert "危险" in result.output


def test_check_shows_no_history_hint(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/check.db")
    with patch("hiveflow.cli.run_health_check", return_value=_no_history_result()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
    assert "sync --days" in result.output


def test_check_exit_code_always_zero(monkeypatch, tmp_path) -> None:
    """无论结论如何，退出码都是 0。"""
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{tmp_path}/check.db")
    with patch("hiveflow.cli.run_health_check", return_value=_danger_result()):
        with patch("hiveflow.cli._load_check_data", return_value=([], {})):
            result = CliRunner().invoke(app, ["check"])
    assert result.exit_code == 0
```

- [ ] **Step 2: 运行确认失败**

```bash
uv run python -m pytest tests/test_cli_check.py -v
```
Expected: FAIL — `check` 命令不存在

- [ ] **Step 3: 在 cli.py 中添加 `check` 命令**

在顶部 import 区添加：

```python
from hiveflow.application.health_check import AlertLevel, HealthCheckResult, run_health_check
from sqlmodel import select
```

在 sync 命令之后添加辅助函数和 check 命令：

```python
def _load_check_data(settings: Settings) -> tuple[list, dict]:
    """从数据库加载 check 所需数据：持仓列表 + 按 symbol 分组的 K 线。"""
    from hiveflow.domain.market_data import MarketBar
    from hiveflow.domain.positions import Position
    create_all_tables(settings)
    with get_session(settings) as session:
        positions = session.exec(select(Position)).all()
        all_bars = session.exec(select(MarketBar)).all()
    bars_by_symbol: dict[str, list] = {}
    for bar in all_bars:
        bars_by_symbol.setdefault(bar.symbol, []).append(bar)
    return list(positions), bars_by_symbol


@app.command()
def check(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """检查持仓风险状态，输出健康结论。"""
    settings = Settings()
    positions, bars_by_symbol = _load_check_data(settings)

    result = run_health_check(positions=positions, bars_by_symbol=bars_by_symbol)

    if output == "json":
        payload = {
            "verdict": result.verdict,
            "summary": result.verdict_summary,
            "has_no_history": result.has_no_history,
            "signals": [
                {
                    "symbol": s.symbol,
                    "max_drawdown_7d": round(s.max_drawdown_7d * 100, 2),
                    "alert_level": s.alert_level.value,
                    "action_hint": s.action_hint,
                }
                for s in result.signals
            ],
        }
        console.print(json.dumps(payload, ensure_ascii=False))
        return

    # Pretty 输出
    from datetime import date
    console.rule(f"今日持仓健康检查  {date.today()}")
    console.print()

    verdict_style = {
        "safe": "bold green",
        "watch": "bold yellow",
        "danger": "bold red",
    }[result.verdict]
    verdict_icon = {"safe": "✅", "watch": "⚠️", "danger": "🔴"}[result.verdict]
    console.print(f"[{verdict_style}][结论] {verdict_icon}  {result.verdict_summary}[/{verdict_style}]")
    console.print()

    if result.has_no_history:
        console.print(
            "[yellow]提示：未检测到历史行情数据，请先执行 hiveflow sync --days 30 以启用风险分析。[/yellow]"
        )
        return

    if result.signals:
        table = Table(box=box.SIMPLE)
        table.add_column("币种", style="bold")
        table.add_column("7日最大回撤", justify="right")
        table.add_column("状态")
        level_display = {
            AlertLevel.NORMAL: ("正常", "green"),
            AlertLevel.WARNING: ("⚠️ 注意", "yellow"),
            AlertLevel.DANGER: ("🔴 危险", "red"),
        }
        for sig in result.signals:
            label, color = level_display[sig.alert_level]
            table.add_row(
                sig.symbol,
                f"{sig.max_drawdown_7d * 100:.1f}%",
                f"[{color}]{label}[/{color}]",
            )
        console.print(table)

    actions = [s.action_hint for s in result.signals if s.action_hint]
    if actions:
        console.print("[bold]建议动作[/bold]")
        for hint in actions:
            console.print(f"  → {hint}")
```

同时在 cli.py 顶部确保以下 import 存在（根据现有内容补充缺少的）：
```python
from hiveflow.db import create_all_tables, get_session
from hiveflow.config import Settings
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run python -m pytest tests/test_cli_check.py -v
```
Expected: 4 passed

- [ ] **Step 5: 全量测试**

```bash
uv run python -m pytest -q
```
Expected: 122 passed

- [ ] **Step 6: 提交**

```bash
git add src/hiveflow/cli.py tests/test_cli_check.py
git commit -m "feat: 新增 check CLI 命令（hiveflow check）"
```

---

## 验收标准

全部任务完成后，执行以下手动验收：

```bash
# 1. 配置 OKX（真实测试可选，测试环境可跳过）
echo "HIVEFLOW_OKX_API_KEY=your_key" >> .env
echo "HIVEFLOW_OKX_API_SECRET=your_secret" >> .env
echo "HIVEFLOW_OKX_API_PASSPHRASE=your_pass" >> .env

# 2. 同步持仓
uv run hiveflow sync

# 3. 同步 30 天 K 线
uv run hiveflow sync --days 30

# 4. 健康检查
uv run hiveflow check

# 5. JSON 输出验证
uv run hiveflow check --output json | python -m json.tool

# 6. 全量测试
uv run python -m pytest -q
```

期望最终测试数：≥ 109 passed（原 87 + 新增 22）
