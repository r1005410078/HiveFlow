# A 股特有信号设计文档（Phase 2-A）

**日期：** 2026-03-24
**状态：** 已审核，待实现
**目标：** 在不破坏现有信号系统的前提下，新增 A 股特有信号：个股层面（PE/PB、涨跌停）和市场层面（北向资金、融资余额）。

---

## 背景与决策

Phase 1 完成了 A 股基础设施（market 字段、CNMarketDataProvider、CSV 导入）。Phase 2-A 在此基础上新增 A 股特有信号，使投资决策系统能感知 A 股的估值水平和市场情绪。

**范围：**
- 个股信号：PE/PB 估值、当日涨跌停触发
- 市场信号：北向资金净流入、融资余额、全市场涨跌停家数
- 数据源：腾讯行情（主）+ akshare（回退/补充）
- akshare 依赖版本：`>=1.14.0`（与 Phase 1 一致，见 `pyproject.toml [cn]`）

**不在本次范围：**
- OKX Provider 接口化（Phase 2-C）
- 跨市场货币折算（Phase 2-D）
- 港股/美股市场扩展（Phase 2-E）
- A 股特有信号与现有 SignalSnapshot 的合并视图
- ST 股、创业板（20% 涨跌幅）、科创板（20%）、北交所（30%）的差异化涨跌停检测（已知限制，Phase 2-A 仅覆盖主板非 ST 股 ±10%）

**Phase 2-B**（券商 API PositionProvider）：已明确推迟，A 股无友好 API，暂不实现。

---

## 整体架构变化

**改动原则：加法为主，不动现有信号路径。**

现有 `build_signal_snapshot` / `SignalSnapshot` 路径保持不变。新增独立路径：

```
腾讯行情（主）    ─┐
akshare（回退）  ─┴→ CNSignalProvider → build_cn_stock_signal  → CNStockSignal
                                      → build_cn_market_signal → CNMarketSignal
```

**返回值设计：** `build_cn_stock_signal` / `build_cn_market_signal` 直接返回落库后的实体（而非 dict），与现有 `build_signal_snapshot` 返回 dict 的模式不同。这是有意为之：新实体结构固定、类型安全，不需要 dict 的灵活性。

---

## Domain 实体

新增文件：`src/hiveflow/domain/cn_signals.py`

```python
from sqlmodel import SQLModel, Field, UniqueConstraint

class CNStockSignal(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("symbol", "date", name="uq_cn_stock_signal_symbol_date"),)

    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    date: str                           # 日期字符串 "YYYY-MM-DD"，唯一约束用
    timestamp: datetime                 # 信号时间（UTC）
    market: str = "cn_a_share"          # 与现有实体 market 字段保持一致
    pe_ratio: float | None = None       # 市盈率（TTM）
    pb_ratio: float | None = None       # 市净率
    limit_up_hit: bool | None = None    # 当日触及涨停（仅主板非 ST ±10%）
    limit_down_hit: bool | None = None  # 当日触及跌停（仅主板非 ST ±10%）

class CNMarketSignal(SQLModel, table=True):
    __table_args__ = (UniqueConstraint("date", name="uq_cn_market_signal_date"),)

    id: int | None = Field(default=None, primary_key=True)
    date: str                                             # 日期字符串 "YYYY-MM-DD"
    timestamp: datetime                                   # 信号时间（UTC）
    northbound_net_flow: float | None = None              # 北向资金净流入（亿元）
    margin_balance: float | None = None                   # 融资余额（亿元，沪深合计）
    limit_up_count: int | None = None                     # 全市场涨停家数
    limit_down_count: int | None = None                   # 全市场跌停家数
```

**去重策略：** 利用 `UniqueConstraint`，写入前先 `DELETE WHERE symbol=? AND date=?`（CNStockSignal）或 `DELETE WHERE date=?`（CNMarketSignal），再 INSERT。与现有 `sync_cn_market_data` 的删前插覆盖模式一致。

两张表通过 `db.py` 的 `_run_lightweight_migrations` 自动建表（`CREATE TABLE IF NOT EXISTS`），存量数据零影响。

---

## Infrastructure 层

新增文件：`src/hiveflow/infrastructure/cn_signal_provider.py`

```python
class CNSignalProvider:
    def __init__(self, settings: Settings | None = None) -> None:
        """
        使用 settings.cn_market_data_source 和 settings.tushare_token。
        腾讯后端无需 token；akshare 后端复用现有 CNMarketDataProvider 的连接逻辑。
        """
        ...

    def fetch_stock_signal(self, symbol: str) -> dict:
        """返回个股信号字段 dict，字段缺失时值为 None。"""
        ...

    def fetch_market_signal(self) -> dict:
        """返回市场信号字段 dict，字段缺失时值为 None。"""
        ...
```

### 数据来源与回退规则

| 字段 | 主数据源 | 回退 | 全部失败 |
|------|---------|------|---------|
| `limit_up_hit` / `limit_down_hit` | 腾讯（最新价 vs 昨收×1.095/0.905） | akshare 当日 K 线最高/最低价推断 | `None` + warning |
| `pe_ratio` / `pb_ratio` | akshare `stock_a_lg_indicator` | 无 | `None` + warning |
| `northbound_net_flow` | akshare `stock_em_hsgt_north_net_flow_in` | 无 | `None` + warning |
| `margin_balance` | akshare 沪深融资余额接口（求和） | 无 | `None` + warning |
| `limit_up_count` / `limit_down_count` | akshare 涨跌停统计接口 | 无 | `None` + warning |

**涨跌停检测逻辑（主板非 ST，±10%）：**
```python
limit_up_hit = last_price >= prev_close * 1.095   # 留 0.5% 容差
limit_down_hit = last_price <= prev_close * 0.905
```

**已知限制：** ST 股（±5%）、创业板/科创板（±20%）、北交所（±30%）使用相同阈值会误判。Phase 2-A 不处理差异化阈值，`limit_up_hit`/`limit_down_hit` 对这些股票可能不准确。

**回退触发条件：** 腾讯接口抛出任何异常即触发 akshare 回退；akshare 失败则字段置 `None` 并 `warnings.warn`，不中断整体流程。

**akshare 函数名稳定性：** akshare 存在跨版本改名风险。Phase 2-A 基于 `akshare>=1.14.0` 的接口名。若升级后接口名变更，在 `cn_signal_provider.py` 中集中更新映射即可。

---

## Application 层

新增文件：`src/hiveflow/application/cn_signals.py`

```python
def build_cn_stock_signal(
    symbol: str,
    settings: Settings | None = None,
) -> CNStockSignal:
    """拉取个股 A 股特有信号并落库（同一 symbol 同一日期覆盖写入）。"""
    ...

def build_cn_market_signal(
    settings: Settings | None = None,
) -> CNMarketSignal:
    """拉取市场级 A 股信号并落库（同一日期覆盖写入）。"""
    ...
```

两者均：
1. 调用 `CNSignalProvider` 获取字段 dict
2. `date = datetime.now().strftime("%Y-%m-%d")`
3. 删除同 symbol+date（或同 date）的旧记录，INSERT 新记录
4. 返回落库后的实体

---

## CLI 变更

在现有 `signal` 命令组下新增两条命令：

```bash
# 个股信号
hiveflow signal cn-stock 000001.SZ
hiveflow signal cn-stock 000001.SZ --output json

# 市场信号
hiveflow signal cn-market
hiveflow signal cn-market --output json
```

**输出示例（cn-stock）：**
```
symbol        : 000001.SZ
date          : 2026-03-24
pe_ratio      : 8.32
pb_ratio      : 0.76
limit_up_hit  : False
limit_down_hit: False
```

**输出示例（cn-market）：**
```
date               : 2026-03-24
northbound_net_flow: 32.5
margin_balance     : 14832.6
limit_up_count     : 43
limit_down_count   : 12
```

数值单位（亿元）在 `--help` 中说明，输出中只显示数字，与现有 CLI 风格一致。
`None` 字段显示为 `N/A`（文本）或 `null`（JSON）。

---

## 测试策略

全部 mock `CNSignalProvider`，不依赖真实网络。

| 测试 | 要点 |
|------|------|
| `test_build_cn_stock_signal_tencent_success` | 腾讯正常，返回含涨跌停的 CNStockSignal |
| `test_build_cn_stock_signal_tencent_fallback` | 腾讯失败，akshare 回退，涨跌停字段有值 |
| `test_build_cn_stock_signal_all_fail` | 全部失败，pe/pb/limit 字段为 None，不抛异常 |
| `test_build_cn_market_signal_success` | 北向、融资、涨跌停家数均有值 |
| `test_build_cn_market_signal_partial_none` | 部分字段 None，其余字段正常 |
| `test_cn_stock_signal_dedup_overwrite` | 同一 symbol 同一日期重复调用，覆盖写入不重复堆积 |
| `test_cn_limit_hit_detection` | 涨停/跌停/正常三种价格分别验证 ±10% 检测逻辑 |
| `test_cli_cn_stock_text_output` | `signal cn-stock` 文本输出含所有字段，None 显示 N/A |
| `test_cli_cn_stock_json_output` | `--output json` 输出合法 JSON，None 字段为 null |
| `test_cli_cn_market_text_output` | `signal cn-market` 文本输出结构正确 |

全量回归基线：当前 390+ passed 不退步。

---

## Phase 2 后续展望（不在本次范围）

- **Phase 2-B**：券商 API PositionProvider（已推迟，A 股无友好 API）
- **Phase 2-C**：OKX Provider 接口化
- **Phase 2-D**：跨市场货币折算与全局组合风险
- **Phase 2-E**：港股/美股市场扩展
