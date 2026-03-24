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
                   positions list（改：加折算列）     src/hiveflow/cli.py
                   portfolio summary（新 CLI 命令）   src/hiveflow/cli.py
```

---

## Domain 变更

### `Position` 加 `currency` 字段

文件：`src/hiveflow/domain/positions.py`

```python
currency: str = "USDT"  # "USDT" | "CNY"，默认值向后兼容存量数据
```

`Position` 实体已有 `market: str = "crypto"` 字段，`PositionWithFx` 直接复用此字段。

**轻量迁移**（文件：`src/hiveflow/db.py`，在 `_run_lightweight_migrations` 中追加）：

```python
pos_col_names = [row[1] for row in conn.exec_driver_sql(
    "PRAGMA table_info(position)"
).fetchall()]
if "currency" not in pos_col_names:
    conn.exec_driver_sql(
        "ALTER TABLE position ADD COLUMN currency VARCHAR DEFAULT 'USDT'"
    )
```

存量行自动获得 `currency="USDT"`，零影响。

### `PositionProvider` 接口（不变）

文件：`src/hiveflow/domain/providers.py`

```python
class PositionProvider(ABC):
    @abstractmethod
    def fetch_positions(self) -> list[Position]:
        """返回当前账户持仓列表。"""
```

---

## Infrastructure 层

### 1. OkxProvider 实现 PositionProvider

文件：`src/hiveflow/infrastructure/okx/okx_provider.py`

- `OkxProvider` 继承 `PositionProvider`
- `fetch_positions()` 返回 `list[Position]`（而非 `list[OkxPosition]`），`currency="USDT"`、`market="crypto"` 填入
- 原有 `OkxPosition` 数据类保留作内部中间结构，不对外暴露
- 现有 `sync_from_okx` 应用层调用不变

### 2. FxRateProvider（新文件）

文件：`src/hiveflow/infrastructure/fx_rate_provider.py`

```python
class FxRateProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        ...

    def get_cny_per_usdt(self) -> tuple[float, str]:
        """
        返回 (汇率, 来源)，永远不抛异常。
        - 汇率：1 USDT = ? CNY
        - 来源："akshare" | "config_fallback"
        akshare 失败时 warnings.warn，然后使用 settings.cny_usdt_rate 回退。
        settings.cny_usdt_rate 保证始终有值（默认 7.25），因此本方法永远返回有效汇率。
        """
```

**数据来源：**
- 主：`akshare.currency_boc_sina(symbol="美元")`，取最新行中间价（`中行折算价` 列）
- 回退：`settings.cny_usdt_rate`（默认 `7.25`）

**Settings 新增字段**（文件：`src/hiveflow/config.py`）：
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
    market: str           # 复用 Position.market（"crypto" | "cn_a_share"）
    currency: str         # 复用 Position.currency（"USDT" | "CNY"）
    quantity: float
    market_value: float           # 原始货币
    market_value_usdt: float
    market_value_cny: float
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

    空持仓处理：若无持仓，返回 PortfolioSummary(positions=[], total_usdt=0.0,
    total_cny=0.0, fx_rate=fx_rate, fx_source=fx_source, breakdown={})。
    """
```

---

## CLI 变更

文件：`src/hiveflow/cli.py`

### `positions list` 升级

在现有表格加两列，底部加合计行和汇率来源。无持仓时显示"暂无持仓"：

```
 symbol    market      数量      市值(USDT)    市值(CNY)    占比（全局）
 BTC       crypto      0.12      8,400         60,900       45%
 ETH       crypto      2.50      6,200         44,950       33%
 000001    cn_a_share  1000      1,724         12,500       9%
 ─────────────────────────────────────────────────────────────────
 合计                            18,324        132,825      100%
 汇率: 7.25 (akshare)
```

### 新增 `portfolio summary` 命令

`portfolio` 作为新的 typer 子命令组，注册到主 app：

```python
portfolio_app = typer.Typer(name="portfolio", help="跨市场组合视图")
app.add_typer(portfolio_app)
```

```bash
hiveflow portfolio summary
hiveflow portfolio summary --output json
```

**文本输出示例：**
```
 总资产（USDT） : 18,324
 总资产（CNY）  : 132,825
 汇率           : 7.25  (akshare)
 ──────────────────────────────
 市场分布
   crypto       : 91%  (16,600 USDT)
   cn_a_share   :  9%  (1,724 USDT)
```

**JSON 输出：** 包含 `total_usdt`、`total_cny`、`fx_rate`、`fx_source`、`breakdown`、`positions` 数组（每项含 `symbol`、`market`、`currency`、`market_value_usdt`、`market_value_cny`、`weight_global`）。

---

## 测试策略

全部 mock `FxRateProvider` 和数据库，不依赖真实网络。

| 测试 | 要点 |
|------|------|
| `test_fx_rate_provider_akshare_success` | akshare 正常，返回 `(rate, "akshare")` |
| `test_fx_rate_provider_akshare_failure_fallback` | akshare 失败，返回 `(config_rate, "config_fallback")`，warn 不抛异常 |
| `test_okx_provider_implements_position_provider` | `isinstance(OkxProvider(...), PositionProvider)` 为 True |
| `test_okx_provider_fetch_positions_currency_usdt` | `fetch_positions()` 返回的每个 `Position.currency == "USDT"` |
| `test_build_portfolio_summary_mixed_currencies` | CNY + USDT 持仓，折算结果正确，breakdown 合计 1.0 |
| `test_build_portfolio_summary_empty` | 无持仓时返回合法 PortfolioSummary，total_usdt=0，breakdown={} |
| `test_build_portfolio_summary_breakdown` | market breakdown 百分比合计 100% |
| `test_migration_adds_currency_column_with_default` | 旧 Position 行迁移后 currency == "USDT" |
| `test_cli_portfolio_summary_text` | 文本输出含总值和汇率来源 |
| `test_cli_portfolio_summary_json` | JSON 输出字段完整 |
| `test_cli_positions_list_fx_columns` | `positions list` 输出含 `市值(CNY)` 列 |

全量回归基线：当前 430+ passed 不退步。
