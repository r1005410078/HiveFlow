# L6 执行层 Phase 1 — 订单生成设计

## Goal

实现 L6 执行层 Phase 1：基于 L4 组合优化权重、L5.5 冲击成本与持久化持仓状态，生成完整订单列表（含 quantity、limit_price、order_type、validity、action）。订单写入 `execution_plan` 字段替换当前空数组，同时维护 DB positions 表跟踪持仓变化。提供独立 HTTP 端点和 CLI 命令。

L6 是本地模拟执行层（Phase 1）：不接券商 API，不发送真实报单，只生成结构化执行计划供运营确认。

## Architecture

```
CLI: hf execution plan --as-of DATE --output json|table
  └─ POST /v1/execution/plan  { as_of, target_weights, pretrade }
       └─ get_execution_service() [dependencies.py]
            └─ run_execution_plan(as_of, target_weights, pretrade, bar_store)
                 ├─ 读 positions 表 → current_positions { symbol: notional }
                 │    （取 MAX(as_of) <= today 的最新快照，无记录则全为 0）
                 ├─ 取 as_of 收盘价（bar_store.list_bars, 1d）
                 ├─ per-symbol:
                 │    delta = target_notional - current_notional
                 │    跳过条件：|delta| / max(current_notional, 1) < 1%
                 │    direction: buy（delta>0）/ sell（delta<0）
                 │    action: open_long / add_long / reduce_long / close_long
                 │    quantity = floor(|delta| / close_price / 100) × 100（A 股 100 股/手）
                 │    limit_price = close × (1 + slippage_bp/10000)（buy）
                 │                = close × (1 - slippage_bp/10000)（sell）
                 │    order_type = "limit"，validity = "day"
                 │    impact_bp: 从 pretrade 透传（按 symbol 查找）
                 ├─ estimated_total_cost_bp = Σ(target_weight × (slippage_bp + impact_bp))
                 └─ upsert positions 表（symbol, as_of, notional=target_notional）

run_daily 在 L5.5 之后插入 L6：
  pretrade_result → execution_result → data.execution_plan（替换现有 {"orders": []}）
```

**CLI 三跳（与 hf risk check / hf pretrade check 一脉相承）：**
1. `POST /api/v1/portfolio/optimize` → target_weights
2. `POST /v1/pretrade/check` → pretrade（含 per-symbol impact_bp）
3. `POST /v1/execution/plan` → execution_plan

**action 判断规则：**

| current_notional | delta | action |
|------------------|-------|--------|
| = 0 | > 0 | open_long |
| > 0 | > 0 | add_long |
| > 0 | < 0，target > 0 | reduce_long |
| > 0 | < 0，target ≈ 0 | close_long |

## Tech Stack

- Python（同其他 application services）
- FastAPI HTTP 路由（同 `routes_pretrade.py` 模式）
- Rust CLI（同 `cmd/pretrade.rs` 模式，三跳）
- DB positions 表（TimescaleDB，新增 migration）
- 无新 Python 依赖

## File Structure

**新增文件：**

| 文件 | 职责 |
|------|------|
| `quant/src/application/execution/__init__.py` | package init |
| `quant/src/application/execution/execution_service.py` | 核心服务：持仓读写 + 订单生成 |
| `quant/src/interfaces/http/routes_execution.py` | HTTP 路由：POST /v1/execution/plan |
| `quant/db/migrations/003_positions.sql` | positions 表 DDL |
| `quant/tests/unit/test_execution_service.py` | 单元测试（mock bar_store + positions） |
| `quant/tests/contract/test_http_execution.py` | 合约测试 |
| `cli/src/cmd/execution.rs` | CLI 命令定义（clap Args） |
| `cli/src/application/handlers/execution.rs` | CLI handler（三跳 + table/JSON 输出） |

**修改文件：**

| 文件 | 修改内容 |
|------|---------|
| `quant/src/application/daily_run_service.py` | L5.5 后插入 L6，替换 `execution_plan={"orders":[]}` |
| `quant/src/interfaces/http/dependencies.py` | 新增 `ExecutionService` 类型 + `get_execution_service()` |
| `quant/src/interfaces/http/app.py` | 注册 routes_execution router |
| `cli/src/infrastructure/http_client.rs` | 新增 `run_execution_plan()` 函数 |
| `cli/src/cmd/mod.rs` | 注册 execution 子命令 |
| `cli/src/application/handlers/mod.rs` | 注册 execution handler |
| `cli/src/application/dispatch.rs` | 路由 `AppCommand::Execution` |

---

## DB Schema

```sql
-- quant/db/migrations/003_positions.sql
CREATE TABLE IF NOT EXISTS positions (
    symbol        TEXT        NOT NULL,
    as_of         DATE        NOT NULL,
    notional      FLOAT       NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, as_of)
);
```

- 读取逻辑：`SELECT symbol, notional FROM positions WHERE as_of = (SELECT MAX(as_of) FROM positions WHERE as_of <= :today)`
- 写入逻辑：`INSERT INTO positions ... ON CONFLICT (symbol, as_of) DO UPDATE SET notional=EXCLUDED.notional, updated_at=now()`
- bar_store=None 时，positions 读写均降级跳过（不抛异常，当前持仓视为全 0）

## Output Schema

HTTP 响应遵循标准 CLI 输出信封，`data` 字段定义如下：

```json
{
  "as_of": "2026-04-01",
  "slippage_bp": 5,
  "estimated_total_cost_bp": 6.4,
  "orders": [
    {
      "symbol": "600519.SH",
      "direction": "buy",
      "action": "open_long",
      "quantity": 100,
      "target_notional": 120000.0,
      "current_notional": 0.0,
      "close_price": 1180.0,
      "limit_price": 1180.59,
      "order_type": "limit",
      "validity": "day",
      "impact_bp": 2.1
    }
  ]
}
```

**字段说明：**

- `slippage_bp`：固定 5（Phase 1 不可配置）
- `quantity`：`floor(|delta| / close_price / 100) × 100`，A 股最小单位 100 股/手
- `limit_price`：buy → `close × (1 + 5/10000)`，sell → `close × (1 - 5/10000)`，保留 2 位小数
- `impact_bp`：从 pretrade 结果按 symbol 查找透传，pretrade=None 时为 null
- `estimated_total_cost_bp`：`Σ(target_weight × (slippage_bp + impact_bp))`，impact_bp=null 时只计 slippage
- `current_notional`：读自 positions 表，无记录时为 0.0

**bar_store 不可用时的降级行为：**

`close_price=null`，`quantity=null`，`limit_price=null`，订单仍产出（direction/action/target_notional 正常），顶层 warnings 追加：

```json
{"code": "EXECUTION_USING_NO_PRICE", "message": "bar_store unavailable; close_price/quantity/limit_price set to null"}
```

**portfolio=None（L4 失败）时：**`data.execution_plan=null`，与 L5/L5.5 一致。

## CLI Output

**Table 模式（--output table，默认）：**

```
as_of: 2026-04-01   orders: 5   total_cost: 6.4bp

Orders
  BUY  600519.SH  open_long   qty=100   notional=120,000   limit=1,180.59   impact=2.1bp
  BUY  300750.SZ  open_long   qty=200   notional=100,000   limit=231.45     impact=3.8bp
  SELL 000858.SZ  close_long  qty=300   notional=0         limit=198.32     impact=1.2bp
```

**JSON 模式（--output json）：** 输出完整信封 JSON，与 HTTP 响应一致。

## Testing Strategy

### 单元测试 `test_execution_service.py`（mock bar_store + positions）

1. 无持仓 + target>0 → action=open_long，direction=buy，quantity/limit_price 正确
2. 有持仓 + target>current → action=add_long
3. 有持仓 + target<current，target>0 → action=reduce_long，direction=sell
4. 有持仓 + target≈0 → action=close_long
5. bar_store=None → close_price/quantity/limit_price=null，warning EXECUTION_USING_NO_PRICE
6. delta≈0（|delta|/max(current,1) < 1%）→ 跳过，不产生订单

### 合约测试 `test_http_execution.py`

1. `POST /v1/execution/plan` 合法 payload → 200，schema 含所有必填字段
2. 缺少 `target_weights` → 422
3. bar_store=None → 200，降级结果 + warning

### Rust CLI 测试

mock HTTP server 返回标准信封，验证：
- table 输出含订单行（BUY/SELL 方向）
- json 输出完整透传响应
- 三跳中任一失败 → error 信封，exit code 非 0

## Future Work (Phase 2)

- 接入券商 API：order 生成后通过经纪商 SDK 实际发单
- order_type 按 L5.5 tradable 动态选择（tradable=false → market order）
- GTC（Good Till Cancelled）支持：大单分批执行
- 执行回报接入：成交价 vs limit_price 的滑点统计
- slippage_bp 参数化：CLI 支持 `--slippage-bp` 参数
