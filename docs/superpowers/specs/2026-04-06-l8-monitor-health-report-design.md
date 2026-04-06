# L8 监控复盘层 Phase 1 — 因子/信号健康报告设计

## Goal

实现 L8 监控复盘层 Phase 1：基于 `run_daily` 输出，生成当日因子健康度、信号覆盖率、风控状态的结构化报告，并给出整体 green/yellow/red 评级。同时提供 HTTP 端点和 CLI 命令，供日常运营巡检使用。

## Architecture

```
CLI: hf monitor health-report --as-of DATE --output json|table
  └─ GET /v1/monitor/health-report?as_of=DATE
       └─ get_health_report_service() [dependencies.py]
            └─ run_health_report(as_of, bar_store) [health_report_service.py]
                 └─ run_daily(as_of, root=None, bar_store)
                      ↓
                 聚合：factor_health + signal_health + risk_health + overall_rating
                      ↓
                 返回结构化 health_report（预留 trend: null）
```

L8 是纯消费层：不重复实现因子/信号计算，直接复用 `run_daily` 的 L2~L5 输出做二次聚合。`run_daily` 不受影响。

## Tech Stack

- Python（同其他 application services）
- FastAPI HTTP 路由（同 `routes_walk_forward.py` 模式）
- Rust CLI（同 `cmd/walk_forward.rs` 模式）
- 无新依赖

## File Structure

**新增文件：**

| 文件 | 职责 |
|------|------|
| `quant/src/application/monitor/__init__.py` | package init |
| `quant/src/application/monitor/health_report_service.py` | 核心服务：调用 run_daily + 聚合逻辑 |
| `quant/src/interfaces/http/routes_monitor.py` | HTTP 路由：GET /v1/monitor/health-report |
| `quant/tests/unit/test_health_report_service.py` | 单元测试（mock run_daily） |
| `quant/tests/contract/test_http_monitor.py` | 合约测试 |
| `cli/src/cmd/monitor.rs` | CLI 命令定义（clap Args） |
| `cli/src/application/handlers/monitor.rs` | CLI handler（table/JSON 格式化） |

**修改文件：**

| 文件 | 修改内容 |
|------|---------|
| `quant/src/interfaces/http/dependencies.py` | 新增 HealthReportService 类型 + get_health_report_service() |
| `quant/src/interfaces/http/app.py` | 注册 routes_monitor router |
| `cli/src/infrastructure/http_client.rs` | 新增 get_health_report() 函数 |
| `cli/src/cmd/mod.rs` | 注册 monitor 子命令 |
| `cli/src/application/handlers/mod.rs` | 注册 monitor handler |
| `cli/src/main.rs` 或 `cli/src/application/mod.rs` | 路由 AppCommand::Monitor |

---

## Output Schema

HTTP 响应遵循标准 CLI 输出信封（`schema_version`, `command`, `run_id`, `status`, `generated_at`, `data`），`data` 字段定义如下：

```json
{
  "as_of": "2026-04-01",
  "overall_rating": "green",
  "factor_health": {
    "total": 8,
    "ok_count": 7,
    "warn_count": 1,
    "miss_count": 0,
    "details": [
      {"factor_name": "momentum_20d", "availability_rate": 0.93, "status": "ok"},
      {"factor_name": "beta_60d",     "availability_rate": 0.62, "status": "warn"}
    ]
  },
  "signal_health": {
    "coverage_rate": 0.89,
    "composite_score_mean": 0.12,
    "composite_score_std": 0.45,
    "status": "ok"
  },
  "risk_health": {
    "regime": "normal",
    "triggered_rules": [],
    "status": "ok"
  },
  "trend": null,
  "run_daily_warnings": []
}
```

**字段说明：**

- `overall_rating`：green / yellow / red，见评级规则
- `factor_health.details[].status`：
  - `ok`：availability_rate >= 0.8
  - `warn`：0.5 <= rate < 0.8
  - `miss`：rate < 0.5
- `signal_health.status`：
  - `ok`：coverage_rate >= 0.7
  - `warn`：0.5 <= coverage_rate < 0.7
  - `miss`：coverage_rate < 0.5
- `risk_health.status`：
  - `ok`：regime = normal，无触发规则
  - `warn`：regime = warning，或有触发规则
  - `crisis`：regime = crisis
- `trend`：预留字段，Phase 1 始终为 null，Phase 2 填充滚动窗口趋势
- `run_daily_warnings`：透传 run_daily 产生的 warnings 列表

**非交易日行为：**

若 `as_of` 为非交易日，`run_daily` 返回 `skipped: true`，`run_health_report` 透传此结果，`overall_rating` 设为 null，其余字段为 null。

## Overall Rating Rules

| 优先级 | 条件 | 评级 |
|--------|------|------|
| 1（最高） | factor miss_count ≥ 1，或 risk regime = crisis，或 signal coverage < 0.5 | red |
| 2 | factor warn_count ≥ 2，或 risk regime = warning，或 signal coverage < 0.7 | yellow |
| 3（默认） | 其余 | green |

规则按优先级从高到低匹配，第一个满足的条件决定最终评级。

## CLI Output

**JSON 模式（--output json）：** 输出完整信封 JSON，与 HTTP 响应一致。

**Table 模式（--output table，默认）：**

```
as_of: 2026-04-01   overall: GREEN

Factor Health
  total=8  ok=7  warn=1  miss=0
  WARN  beta_60d  62%

Signal Health
  coverage=89%  mean=0.12  std=0.45

Risk
  regime=normal  triggered=0
```

## Testing Strategy

### 单元测试 `test_health_report_service.py`

所有测试 mock `run_daily`，覆盖：

1. 全因子 ok，signal ok，regime normal → overall green
2. 2 个因子 warn，其余 ok → overall yellow
3. 1 个因子 miss → overall red
4. regime = crisis → overall red
5. signal coverage < 0.5 → overall red
6. signal_matrix 为 null（L3 失败）→ signal_health.status = miss，触发 red
7. risk_gate 为 null（L5 失败）→ risk_health.status = ok（宽松处理），不影响评级
8. run_daily 抛异常 → 返回包含 error 信息的 red 报告，不崩溃
9. 非交易日 → overall_rating = null，skipped = true

### 合约测试 `test_http_monitor.py`

1. `GET /v1/monitor/health-report?as_of=2026-04-01` → 200，schema 含所有必填字段
2. 无 as_of 参数 → 422
3. DB 不可用（bar_store=None）→ 200，降级到 deterministic 快照

### Rust CLI 测试

mock HTTP server 返回标准信封，验证：
- table 输出含 overall_rating 行
- json 输出可完整透传响应

## Future Work (Phase 2)

- `trend` 字段：取最近 20 交易日快照，计算因子可用率均值/标准差趋势，识别持续劣化
- 收益归因：待 L6 成交回报接入后，拆解 signal/execution 贡献
- 因子失效预警：连续 N 日 warn 自动触发告警
