# Phase 2-C/D：OKX Provider 接口化 + 跨市场货币折算设计文档

**日期：** 2026-03-24
**状态：** 已审核，待实现
**目标：** 让 OKX 实现 `PositionProvider` 抽象接口，并引入 `FxRateProvider` 支持 CNY/USDT 双货币折算，使 `positions list` 和新增 `portfolio summary` 命令能展示跨市场统一视图。

---

## 背景与决策

Phase 2-A 完成了 A 股特有信号。Phase 2-C/D 在此基础上：
- **2-C**：让 `OkxProvider` 实现 `PositionProvider` 抽象接口，消除应用层对 OKX 具体实现的直接耦合
- **2-D**：引入 `FxRateProvider`（akshare 主 + `.env` 回退），支持 CNY/USDT 双货币折算，并在 `positions list` 和 `portfolio summary` 中展示跨市场统一视图

**范围外：**
- 港股/美股市场扩展（明确不做）
- 历史汇率落库与回溯查询（过度设计，不做）
- A 股 PositionProvider 实现（券商 API 无友好接口，Phase 2-B 已推迟）

---

## 整体架构

**改动原则：加法为主，现有 OKX sync 路径不破坏。**

```
FxRateProvider（新）      ─┐
OkxProvider（改）         ─┤→ build_portfolio_summary（新）→ PortfolioSummary
                           ↓
                   positions list（改：加折算列）
                   portfolio summary（新 CLI 命令）
```

---

## Domain 变更

### `Position` 加 `currency` 字段

文件：`src/hiveflow/domain/positions.py`

```python
currency: str = "USDT"  # "USDT" | "CNY"，默认值向后兼容存量数据
```

存量 SQLite 数据零影响：`db.py` 的 `_run_lightweight_migrations` 使用 `CREATE TABLE IF NOT EXISTS`，新列通过 SQLModel 的 `ALTER TABLE ... ADD COLUMN ... DEFAULT 'USDT'` 轻量迁移添加。

### `PositionProvider` 接口（不变）

文件：`src/hiveflow/domain/providers.py`

```python
class PositionProvider(ABC):
    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        """返回当前账户持仓列表。"""
```

接口不变，OkxProvider 实现它。

---

## Infrastructure 层

### 1. OkxProvider 实现 PositionProvider

文件：`src/hiveflow/infrastructure/okx/okx_provider.py`

- `OkxProvider` 继承 `PositionProvider`
- `fetch_positions()` 返回 `list[Position]`（而非 `list[OkxPosition]`），`currency="USDT"` 填入
- 原有 `OkxPosition` 数据类保留作内部中间结构，不对外暴露
- 现有 `sync_from_okx` 应用层调用不变（仍调用 `provider.fetch_positions()`，只是现在返回的是 domain 实体）

### 2. FxRateProvider（新文件）

文件：`src/hiveflow/infrastructure/fx_rate_provider.py`

```python
class FxRateProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        ...

    def get_cny_per_usdt(self) -> tuple[float, str]:
        """
        返回 (汇率, 来源)。
        - 汇率：1 USDT = ? CNY
        - 来源："akshare" | "config_fallback"
        akshare 失败时 warnings.warn + 使用 settings.cny_usdt_rate 回退。
        """
```

**数据来源：**
- 主：`akshare.currency_boc_sina(symbol="美元")`，取最新行中间价（`中行折算价` 列）
- 回退：`settings.cny_usdt_rate`（默认 `7.25`）

**Settings 新增字段**（`src/hiveflow/config.py`）：
```python
cny_usdt_rate: float = 7.25  # env: HIVEFLOW_CNY_USDT_RATE，FxRateProvider 回退值
```

---

## Application 层

### build_portfolio_summary（新文件）

文件：`src/hiveflow/application/portfolio.py`

```python
@dataclass
class PositionWithFx:
    symbol: str
    market: str
    currency: str
    quantity: float
    market_value: float           # 原始货币
    market_value_usdt: float | None
    market_value_cny: float | None
    weight_global: float          # 占全局总值（USDT 基准）

@dataclass
class PortfolioSummary:
    positions: list[PositionWithFx]
    total_usdt: float
    total_cny: float
    fx_rate: float                # 本次使用的汇率（1 USDT = ? CNY）
    fx_source: str                # "akshare" | "config_fallback"
    breakdown: dict[str, float]   # {"crypto": 0.85, "cn_a_share": 0.15}

def build_portfolio_summary(settings: Settings | None = None) -> PortfolioSummary:
    """
    从数据库读所有 Position，按 currency 折算为 USDT 和 CNY 两套总值。
    折算逻辑：
    - currency="USDT"：market_value_usdt = market_value；market_value_cny = market_value * fx_rate
    - currency="CNY"：market_value_cny = market_value；market_value_usdt = market_value / fx_rate
    weight_global 基于 USDT 总值计算。
    """
```

---

## CLI 变更

### `positions list` 升级

在现有表格中新增两列（需要 FX 时才调用 `FxRateProvider`）：

```
 symbol    market      数量      市值(USDT)    市值(CNY)    占比（全局）
 BTC       crypto      0.12      8,400         60,900       45%
 ETH       crypto      2.50      6,200         44,950       33%
 000001    cn_a_share  1000      —             12,500       7%
 ─────────────────────────────────────────────────────────────────
 合计                            14,600        133,725      100%
 汇率: 7.25 (akshare)
```

FX 获取失败时，CNY 列显示 `N/A`，不中断输出。

### 新增 `portfolio summary` 命令

```bash
hiveflow portfolio summary
hiveflow portfolio summary --output json
```

**文本输出示例：**
```
 总资产（USDT） : 18,600
 总资产（CNY）  : 134,850
 汇率           : 7.25  (akshare)
 ──────────────────────────────
 市场分布
   crypto       : 85%  (15,810 USDT)
   cn_a_share   : 15%  (2,790 USDT)
```

**JSON 输出：** 包含 `total_usdt`、`total_cny`、`fx_rate`、`fx_source`、`breakdown`、`positions` 数组。

---

## 测试策略

全部 mock `FxRateProvider` 和 `OkxProvider`，不依赖真实网络。

| 测试 | 要点 |
|------|------|
| `test_fx_rate_provider_akshare_success` | akshare 正常，返回 (rate, "akshare") |
| `test_fx_rate_provider_akshare_failure_fallback` | akshare 失败，返回 (config_rate, "config_fallback") |
| `test_okx_provider_implements_position_provider` | OkxProvider 是 PositionProvider 的实例 |
| `test_okx_provider_fetch_positions_currency_usdt` | fetch_positions() 返回的 Position.currency == "USDT" |
| `test_build_portfolio_summary_mixed_currencies` | CNY + USDT 持仓，折算结果正确 |
| `test_build_portfolio_summary_fx_failure` | FX 失败时 market_value_cny 为 None，不抛异常 |
| `test_portfolio_summary_breakdown` | market breakdown 百分比合计 100% |
| `test_cli_portfolio_summary_text` | 文本输出含总值和汇率来源 |
| `test_cli_portfolio_summary_json` | JSON 输出字段完整 |
| `test_cli_positions_list_fx_columns` | positions list 含折算列 |

全量回归基线：当前 430+ passed 不退步。

---

## 后续展望（不在本次范围）

- A 股 PositionProvider（Phase 2-B，券商 API 待定）
- 历史汇率落库与组合价值回溯
- 港股/美股扩展（明确不做）
