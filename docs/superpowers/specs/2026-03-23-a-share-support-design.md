# A 股支持设计文档（Phase 1）

**日期：** 2026-03-23
**状态：** 已审核，待实现
**目标：** 在不破坏现有加密功能的前提下，加入 A 股持仓管理与行情分析能力。

---

## 前置依赖

**本设计依赖以下计划先完成：**

- `docs/superpowers/plans/2026-03-23-signal-explicit-symbol-refactor.md`

  该计划将 `build_signal_snapshot` 改为接受显式 `symbol: str` 参数。本设计的信号系统部分（`detect_market(symbol)` 分发、`SIGNAL_PARAMS` 查表）建立在该重构完成后的接口上。两份计划在 `signals.py` 和 `cli.py` 上存在改动交集，必须按顺序落地。

---

## 背景与决策

- **范围：** 自动行情拉取 + 分析，交易手动（不做自动执行）
- **组合模式：** 独立为主 + 可选合并视图（加密和 A 股各自独立运行，`--market all` 时出合并聚合）
- **市场识别：** 自动按 symbol 格式判断，无需用户额外指定
- **数据源：** 可插拔（akshare / tushare，配置切换）
- **持仓导入：** CSV 优先，接口设计支持后续扩展券商 API

**不在 Phase 1 范围内：**
- A 股特有信号（北向资金、涨跌停触发率、融资余额等）
- 跨市场货币合算（CNY vs USDT）
- 券商 API 持仓自动同步
- OKX 现有路径的 Provider 抽象重构（OKX 路径在 Phase 1 保持不动）

---

## 整体架构变化

**改动原则：加法为主，不动现有加密路径。**

OKX 的现有 `sync.py`、`okx_provider.py` 等文件在 Phase 1 **保持不变**。Provider 抽象接口仅为新增的 A 股路径所用；OKX 路径的 Provider 接口化留到 Phase 2。

```
现有路径（不动）:
  OKX API → (现有 sync.py / okx_provider.py) → market-data sync / positions sync

新增路径:
  CSV           → import_cn_positions_from_csv()  → positions import-csv
  akshare/tushare → CNMarketDataProvider           → application/cn_sync.py → market-data sync --market cn

共用路径（market-aware）:
  risk-analysis / signal / summary → 按 market 字段自动选参数
```

---

## Symbol 自动检测

```python
# domain/market.py
import re

CRYPTO = "crypto"
CN_A_SHARE = "cn_a_share"

ANNUALIZATION_FACTOR = {CRYPTO: 365, CN_A_SHARE: 252}
TRADING_DAYS = {CRYPTO: 365, CN_A_SHARE: 252}

def detect_market(symbol: str) -> str:
    """根据 symbol 格式自动判断市场。
    000001.SZ / 600000.SH / 300001.BJ → cn_a_share
    其他 → crypto
    """
    if re.match(r'^\d{6}\.(SH|SZ|BJ)$', symbol.strip().upper()):
        return CN_A_SHARE
    return CRYPTO
```

---

## Provider 接口（Clean Architecture）

按 Clean Architecture 原则，抽象接口属于 **`domain/`**，具体实现属于 **`infrastructure/`**。

```python
# domain/providers.py  ← 新建
from abc import ABC, abstractmethod
from hiveflow.domain.models import MarketBar, Position

class MarketDataProvider(ABC):
    @abstractmethod
    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]: ...

class PositionProvider(ABC):
    @abstractmethod
    def fetch_positions(self) -> list[Position]: ...
```

**Phase 1 只新增 A 股侧的实现：**

```
infrastructure/cn_market_data_provider.py  ← CNMarketDataProvider（新增）
```

OKX 侧不实现 `MarketDataProvider` 接口（Phase 2 再做），保持现有代码不动。

---

## A 股行情同步

### Application 层

新增 `application/cn_sync.py`：

```python
# application/cn_sync.py
def sync_cn_market_data(
    symbols: list[str],
    days: int,
    settings: Settings | None = None,
) -> SyncResult:
    """使用 CNMarketDataProvider 拉取 A 股行情并落库。"""
    s = settings or Settings()
    provider = CNMarketDataProvider(source=s.cn_market_data_source, token=s.tushare_token)
    bars = provider.fetch_bars(symbols, days)
    # 写入 MarketBar，market 字段自动由 detect_market(symbol) 填充
    ...
```

### Infrastructure 层

```python
# infrastructure/cn_market_data_provider.py
class CNMarketDataProvider(MarketDataProvider):
    def __init__(self, source: str, token: str = ""):
        self._source = source  # "akshare" | "tushare"
        self._token = token

    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]:
        if self._source == "akshare":
            return self._fetch_via_akshare(symbols, days)
        return self._fetch_via_tushare(symbols, days)
```

两个后端共用同一个 `MarketBar` 实体落库，上层不感知差异。

---

## A 股持仓导入

CSV 导入**不走 `PositionProvider` 接口**（该接口面向长期持仓同步连接；CSV 是一次性文件导入）。改为在 `application/positions.py` 新增函数，与现有 `import_positions_from_csv` 风格一致：

```python
# application/positions.py 新增
def import_cn_positions_from_csv(file_path: str, settings: Settings | None = None) -> ImportResult:
    """从 CSV 导入 A 股持仓。

    校验规则：
    1. symbol 必须匹配 detect_market(symbol) == CN_A_SHARE，否则报错
    2. CSV 的 market 列（若存在）必须与 detect_market 结果一致，否则报错
    3. 重复导入同一 symbol 则覆盖写入
    """
    ...
```

**CSV 格式契约：**

```
symbol,quantity,avg_cost,market_value
000001.SZ,1000,12.50,13200
600000.SH,500,8.80,4600
```

`market` 列可选；若存在且与 symbol 推断结果不一致，则返回结构化错误（exit code 1）。

---

## Domain 实体变更

**需要加 `market` 字段的实体：**

| 实体 | 迁移方式 |
|------|---------|
| `MarketBar` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |
| `Position` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |
| `TargetAllocation` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |
| `RiskSignal` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |
| `StrategyRun` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |
| `SignalSnapshot` | `ADD COLUMN market VARCHAR DEFAULT 'crypto'` |

全部使用现有轻量迁移模式，存量数据自动填 `'crypto'`，零破坏。

**`db.py` 变更：** 在 `_run_lightweight_migrations()` 函数中为上述六张表各追加一个 `ADD COLUMN market VARCHAR DEFAULT 'crypto'` 迁移块（参考现有 `strategy.dimension` 迁移的写法）。

**SignalSnapshot 写入路径：** `build_signal_snapshot(symbol)` 落库时，从 `detect_market(symbol)` 取 market 值并写入 `SignalSnapshot.market` 字段，保证列有值而非 NULL。

**不需要改的实体：** `Strategy`、`StrategySlot`、`BacktestResult`、`PortfolioSnapshot`、`BlendConfig`、`DecisionLog`。

---

## 配置

新增配置项（`config.py` / `.env`）：

```
HIVEFLOW_CN_MARKET_DATA_SOURCE=akshare   # 或 tushare
HIVEFLOW_TUSHARE_TOKEN=                  # tushare 时必填
```

akshare / tushare 作为可选依赖（`pyproject.toml` `[project.optional-dependencies]`），和现有 PyPortfolioOpt 一样——未安装时命令报错提示，不影响加密功能。

`hiveflow doctor` 自动检查 A 股相关依赖是否安装。

---

## CLI 变更

### 新增命令

| 命令 | 说明 |
|------|------|
| `positions import-csv <file>` | 从 CSV 导入 A 股持仓（调用 `import_cn_positions_from_csv`）|
| `market-data sync --market cn --symbols 000001.SZ,600000.SH` | 拉取 A 股行情（调用 `cn_sync.sync_cn_market_data`）|
| `summary --market all` | 合并视图（见下方 JSON 契约）|

### 已有命令扩展（向后兼容，默认 `crypto`）

| 命令 | 默认行为不变 | 新增参数 |
|------|------------|---------|
| `positions list` | 只显示 crypto | `--market cn / all` |
| `positions drift` | crypto | `--market cn` |
| `risk-analysis assets` | crypto symbols | `--market cn / all` |
| `targets list / generate` | crypto | `--market cn` |
| `rebalance preview` | crypto | `--market cn` |
| `signal snapshot` | crypto symbols | 自动按 symbol format 判断（依赖 symbol-refactor 先完成）|

### `summary --market all` JSON 契约

```json
{
  "markets": {
    "crypto": {
      "position_count": 3,
      "total_market_value_usdt": 12000.00,
      "currency": "USDT"
    },
    "cn_a_share": {
      "position_count": 2,
      "total_market_value_cny": 17800.00,
      "currency": "CNY"
    }
  },
  "note": "跨市场货币未合算，各市场独立展示"
}
```

`--output json` 时严格输出此结构，不含 `total_value` 跨市场合计字段（Phase 2 再议）。

### 不改的命令（加密专属）

`trade execute`、`positions sync`（OKX）、`market-data sync`（不加 `--market` 时默认 crypto）

---

## 风险引擎

`compute_volatility`、`compute_drawdown`、`compute_portfolio_risk` 改为接受 `annualization_factor` 参数（默认 365 保持向后兼容）：

```python
def compute_volatility(returns, annualization_factor: int = 365) -> dict: ...
```

调用方（`application/risk_analysis.py`）先 `detect_market`，再传对应因子。`--market all` 时分市场各算，不跨市场混算。

---

## 信号系统（Phase 1 保守策略）

**前提：** `signal-explicit-symbol-refactor` 计划已完成，`build_signal_snapshot(symbol: str)` 已接受显式 symbol。

在此基础上：
- `build_signal_snapshot(symbol)` 内部调用 `detect_market(symbol)` 决定 `SIGNAL_PARAMS`
- 落库时将 market 写入 `SignalSnapshot.market`
- 输出的 signal 对象新增 `"market"` 字段

```python
SIGNAL_PARAMS = {
    "crypto":     {"ma_short": 7,  "ma_long": 30, "vol_window": 30},
    "cn_a_share": {"ma_short": 5,  "ma_long": 20, "vol_window": 20},
}
```

A 股特有信号（北向资金、涨跌停等）留到 Phase 2。

---

## 测试策略

### 新增测试覆盖点

| 测试 | 要点 |
|------|------|
| `test_detect_market_cn_symbols` | `000001.SZ`、`600000.SH`、`300001.BJ` 各返回 `cn_a_share`；大小写不敏感 |
| `test_detect_market_crypto_symbols` | `BTC`、`ETH`、`000001`（无后缀）返回 `crypto` |
| `test_detect_market_invalid_format` | 格式错误不抛异常，退化为 `crypto` |
| `test_cn_market_data_provider_akshare` | mock akshare，验证 `MarketBar.market == "cn_a_share"` |
| `test_cn_market_data_provider_tushare` | mock tushare，验证相同落库结果 |
| `test_import_cn_positions_valid_csv` | 正常导入，验证 `Position.market == "cn_a_share"` |
| `test_import_cn_positions_market_mismatch` | CSV `market` 列与 symbol 不符，返回结构化错误 exit_code=1 |
| `test_import_cn_positions_crypto_symbol_rejected` | CSV 含 `BTC` symbol，被校验拒绝 |
| `test_import_cn_positions_duplicate_overwrite` | 重复导入同一 symbol 覆盖写入，不重复堆积 |
| `test_lightweight_migration_adds_market_column` | 验证旧库在迁移后可正常读写，存量数据 market 默认为 `'crypto'` |
| `test_compute_volatility_cn_annualization` | 传 `annualization_factor=252`，验证结果与 365 不同 |
| `test_signal_snapshot_cn_writes_market_field` | A 股 symbol 触发后，`SignalSnapshot.market == "cn_a_share"` |
| `test_summary_all_markets_json_schema` | `--market all --output json` 输出含 `markets.crypto` 和 `markets.cn_a_share`，无 `total_value` |

### 测试原则

- 所有新 Provider 使用 mock，不依赖真实外部 API
- 全量回归基线：当前 280+ passed 不退步
- 每个 Chunk 完成后立即跑 `uv run pytest -q` 验证

---

## Phase 2 展望（不在当前范围）

- A 股特有信号（北向资金、涨跌停触发率、融资余额、PE/PB 估值信号）
- 券商 API `PositionProvider` 实现（读仓，不下单）
- OKX 现有路径重构为 `OKXMarketDataProvider` / `OKXPositionProvider` 实现 Provider 接口
- 跨市场货币折算与全局组合风险
- 港股 / 美股市场扩展（第三个 market）
