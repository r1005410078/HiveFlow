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

**不在本次范围：**
- OKX Provider 接口化
- 跨市场货币折算
- 港股/美股市场扩展
- A 股特有信号与现有 SignalSnapshot 的合并视图

---

## 整体架构变化

**改动原则：加法为主，不动现有信号路径。**

现有 `build_signal_snapshot` / `SignalSnapshot` 路径保持不变。新增独立路径：

```
腾讯行情（主）    ─┐
akshare（回退）  ─┴→ CNSignalProvider → build_cn_stock_signal  → CNStockSignal
                                      → build_cn_market_signal → CNMarketSignal
```

---

## Domain 实体

新增文件：`src/hiveflow/domain/cn_signals.py`

```python
class CNStockSignal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    symbol: str
    timestamp: datetime
    pe_ratio: float | None = None       # 市盈率（TTM）
    pb_ratio: float | None = None       # 市净率
    limit_up_hit: bool | None = None    # 当日触及涨停
    limit_down_hit: bool | None = None  # 当日触及跌停

class CNMarketSignal(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    timestamp: datetime
    northbound_net_flow: float | None = None  # 北向资金净流入（亿元）
    margin_balance: float | None = None       # 融资余额（亿元，沪深合计）
    limit_up_count: int | None = None         # 全市场涨停家数
    limit_down_count: int | None = None       # 全市场跌停家数
```

两张表通过 `db.py` 的 `_run_lightweight_migrations` 自动建表（`CREATE TABLE IF NOT EXISTS`），存量数据零影响。

---

## Infrastructure 层

新增文件：`src/hiveflow/infrastructure/cn_signal_provider.py`

```python
class CNSignalProvider:
    def __init__(self, settings: Settings | None = None): ...

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
| `limit_up_hit` / `limit_down_hit` | 腾讯（最新价 vs 昨收×1.095/0.905） | akshare 当日 K 线 | `None` + warning |
| `pe_ratio` / `pb_ratio` | akshare `stock_a_lg_indicator` | 无 | `None` + warning |
| `northbound_net_flow` | akshare `stock_em_hsgt_north_net_flow_in` | 无 | `None` + warning |
| `margin_balance` | akshare 沪深融资余额接口（求和） | 无 | `None` + warning |
| `limit_up_count` / `limit_down_count` | akshare 涨跌停统计 | 无 | `None` + warning |

**涨跌停检测逻辑：**
```python
limit_up_hit = last_price >= prev_close * 1.095   # 留 0.5% 容差
limit_down_hit = last_price <= prev_close * 0.905
```

**回退触发条件：** 腾讯接口抛出任何异常（连接超时、解析失败等）即触发 akshare 回退；akshare 失败则字段置 `None` 并 `warnings.warn`，不中断整体流程。

---

## Application 层

新增文件：`src/hiveflow/application/cn_signals.py`

```python
def build_cn_stock_signal(
    symbol: str,
    settings: Settings | None = None,
) -> CNStockSignal:
    """拉取个股 A 股特有信号并落库。"""
    ...

def build_cn_market_signal(
    settings: Settings | None = None,
) -> CNMarketSignal:
    """拉取市场级 A 股信号并落库。"""
    ...
```

两者均：
1. 调用 `CNSignalProvider` 获取字段 dict
2. 构造对应实体并写入数据库（按 `(symbol, timestamp.date())` / `timestamp.date()` 覆盖写入，避免重复）
3. 返回落库后的实体

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
symbol      : 000001.SZ
timestamp   : 2026-03-24 15:00:00
pe_ratio    : 8.32
pb_ratio    : 0.76
limit_up_hit: False
limit_down_hit: False
```

**输出示例（cn-market）：**
```
timestamp          : 2026-03-24 15:30:00
northbound_net_flow: 32.5 亿元
margin_balance     : 14832.6 亿元
limit_up_count     : 43
limit_down_count   : 12
```

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
| `test_cn_limit_hit_detection` | 涨停/跌停/正常三种价格分别验证检测逻辑 |

全量回归基线：当前 390+ passed 不退步。

---

## Phase 2 后续展望（不在本次范围）

- **Phase 2-C**：OKX Provider 接口化
- **Phase 2-D**：跨市场货币折算与全局组合风险
- **Phase 2-E**：港股/美股市场扩展
