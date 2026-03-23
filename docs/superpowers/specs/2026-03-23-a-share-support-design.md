# A 股支持设计文档（Phase 1）

**日期：** 2026-03-23
**状态：** 已审核，待实现
**目标：** 在不破坏现有加密功能的前提下，加入 A 股持仓管理与行情分析能力。

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

---

## 整体架构变化

**改动原则：加法为主，不动现有加密路径。**

```
现有路径（不动）:
  OKX API → OKXPositionProvider → positions sync
  OKX API → OKXMarketDataProvider → market-data sync

新增路径:
  CSV           → CSVPositionProvider   → positions import-csv
  akshare/tushare → CNMarketDataProvider → market-data sync --market cn

共用路径（market-aware）:
  risk-analysis / signal / summary → 按 market 字段自动选参数
```

新增两个 infrastructure 抽象接口：

```python
# infrastructure/market_data_provider.py
class MarketDataProvider(ABC):
    def fetch_bars(self, symbols: list[str], days: int) -> list[MarketBar]: ...

# infrastructure/position_provider.py
class PositionProvider(ABC):
    def fetch_positions(self) -> list[Position]: ...
```

OKX 现有逻辑原地重构为这两个接口的实现，不改行为。

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

**不需要改的实体：** `Strategy`、`StrategySlot`、`BacktestResult`、`PortfolioSnapshot`、`BlendConfig`、`DecisionLog`。

---

## 数据提供者

### CNMarketDataProvider

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

### CSVPositionProvider

CSV 格式契约（参考现有 `market-data template` 设计）：

```
symbol,quantity,avg_cost,market_value,market
000001.SZ,1000,12.50,13200,cn_a_share
600000.SH,500,8.80,4600,cn_a_share
```

- 导入时自动按 `detect_market(symbol)` 校验 `market` 字段一致性
- 重复导入同一 symbol 则覆盖写入（与现有 `targets import append` 语义一致）

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
| `positions import-csv <file>` | 从 CSV 导入 A 股持仓 |
| `market-data sync --market cn --symbols 000001.SZ,600000.SH` | 拉取 A 股行情 |
| `summary --market all` | 合并视图：加密 + A 股汇总（不做跨市场货币合算）|

### 已有命令扩展（向后兼容，默认 `crypto`）

| 命令 | 默认行为不变 | 新增参数 |
|------|------------|---------|
| `positions list` | 只显示 crypto | `--market cn / all` |
| `positions drift` | crypto | `--market cn` |
| `risk-analysis assets` | crypto symbols | `--market cn / all` |
| `targets list / generate` | crypto | `--market cn` |
| `rebalance preview` | crypto | `--market cn` |
| `signal snapshot` | crypto symbols | 自动按 symbol format 判断 |

### 不改的命令（加密专属）

`trade execute`、`positions sync`（OKX）、`market-data sync`（不加 `--market` 时默认 crypto）

---

## 风险引擎与信号系统

### 风险引擎

`compute_volatility`、`compute_drawdown`、`compute_portfolio_risk` 改为接受 `annualization_factor` 参数：

```python
def compute_volatility(returns, annualization_factor: int = 365) -> dict: ...
```

调用方（`application/risk_analysis.py`）先 `detect_market`，再传对应因子。`--market all` 时分市场各算，不跨市场混算。

### 信号系统（Phase 1 保守策略）

- `build_signal_snapshot(symbol)` 内部先 `detect_market(symbol)`
- 市场感知参数从 `SIGNAL_PARAMS` 按 market 查表
- 输出的 signal 对象新增 `"market"` 字段

```python
SIGNAL_PARAMS = {
    "crypto":     {"ma_short": 7,  "ma_long": 30, "vol_window": 30},
    "cn_a_share": {"ma_short": 5,  "ma_long": 20, "vol_window": 20},
}
```

A 股特有信号（北向资金、涨跌停等）留到 Phase 2。

---

## 合并视图边界

- `summary --market all`：加密总市值（USDT）+ A 股总市值（CNY）并排展示，**不做跨市场货币合算**
- `risk-analysis assets --market all`：分市场各出一张相关性矩阵，不跨市场混算
- 跨市场货币折算与全局组合风险留到 Phase 2

---

## 测试策略

- 每个新 Provider 使用 mock 数据，不依赖真实外部 API（与现有 OKX 测试方式一致）
- `detect_market` 函数覆盖边界用例（大小写、格式错误等）
- 轻量迁移测试：验证存量 crypto 数据在加 `market` 列后仍可正常读取
- 风险引擎参数化测试：相同数据传不同 `annualization_factor`，验证结果差异符合预期
- 全量回归基线：当前 280+ passed 不退步

---

## Phase 2 展望（不在当前范围）

- A 股特有信号（北向资金、涨跌停触发率、融资余额、PE/PB 估值信号）
- 券商 API `PositionProvider` 实现（读仓，不下单）
- 跨市场货币折算与全局组合风险
- A 股 `trade execute`（券商 API，读写）
- 港股 / 美股市场扩展（第三个 market）
