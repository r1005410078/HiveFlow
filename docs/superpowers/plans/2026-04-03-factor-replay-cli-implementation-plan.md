# Factor Replay CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `factor optimize replay` 正式接入 Rust CLI，提供统一命令 `hf factor replay`，支持 `json/table` 输出并复用现有 evaluate 接口。

**Architecture:** 在 `cli/src/cmd` 新增 `factor replay` 子命令；`application` 新增 replay 编排 handler（逐日调用 `POST /api/v1/factor-optimization/evaluate` 并聚合 summary）；`infrastructure/table_renderer` 新增 replay 表格渲染。保持 `cmd -> application -> domain` 与 `application -> infrastructure` 方向，不在 `cmd` 写业务流程。

**Tech Stack:** Rust (`clap`, `serde_json`, `reqwest`, `comfy-table`), date arithmetic with `chrono`.

---

## 0. 文件与职责

- Modify: `cli/Cargo.toml`（新增 `chrono` 依赖）
- Modify: `cli/src/application/requests.rs`（新增 `FactorReplayRequest` 与 `AppCommand::FactorReplay`）
- Modify: `cli/src/cmd/factor.rs`（新增 `Replay` 子命令与参数解析）
- Modify: `cli/src/cmd/mod.rs`（将 `factor replay` 映射到 `AppCommand`）
- Modify: `cli/src/application/handlers/mod.rs`（注册 `factor_replay`）
- Create: `cli/src/application/handlers/factor_replay.rs`（逐日回放与聚合逻辑）
- Modify: `cli/src/application/dispatch.rs`（调度 `AppCommand::FactorReplay`）
- Modify: `cli/src/infrastructure/table_renderer.rs`（新增 `render_factor_replay_table`）
- Create: `cli/tests/http_factor_replay.rs`（回放编排与错误路径）
- Create: `cli/tests/http_factor_replay_table.rs`（table 渲染断言）

---

### Task 1: 先写失败测试（Replay 编排 + 聚合）

**Files:**
- Create: `cli/tests/http_factor_replay.rs`

- [x] **Step 1: 写回放成功路径失败测试（逐日请求 + summary 聚合）**

```rust
use hf_cli::application::handlers::factor_replay::run_replay;
use hf_cli::application::requests::FactorReplayRequest;
use mockito::Server;

#[test]
fn factor_replay_runs_daily_evaluate_and_builds_summary() {
    let mut server = Server::new();

    let _m1 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
            "correlation_threshold": 0.7
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"pass","blocking_reasons":[],"watch_items":[]},"correlation_analysis":{"alert_count":0},"top_combinations":{"items":[{"factors":["momentum_20","inv_volatility_20"]}]}}}"#)
        .create();

    let _m2 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-04-02",
            "end_date": "2026-04-02",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
            "correlation_threshold": 0.7
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"watch","blocking_reasons":[],"watch_items":["alert_count_watch:2"]},"correlation_analysis":{"alert_count":2},"top_combinations":{"items":[{"factors":["momentum_20","max_drawdown_60"]}]}}}"#)
        .create();

    let req = FactorReplayRequest {
        start_date: "2026-04-01".to_string(),
        end_date: "2026-04-02".to_string(),
        factor_names: vec!["momentum_20".to_string(), "inv_volatility_20".to_string()],
        correlation_threshold: Some(0.7),
        output: "json".to_string(),
    };

    let out = run_replay(&server.url(), 1000, &req).expect("replay should succeed");

    assert_eq!(out["summary"]["days"], 2);
    assert_eq!(out["summary"]["error_days"], 0);
    assert_eq!(out["summary"]["pass_days"], 1);
    assert_eq!(out["summary"]["watch_days"], 1);
    assert_eq!(out["summary"]["fail_days"], 0);
    assert_eq!(out["summary"]["top1_change_days"], 1);
    assert_eq!(out["daily_items"].as_array().unwrap().len(), 2);
}
```

- [x] **Step 2: 写抓取失败路径失败测试（error_days 与 unknown 状态）**

```rust
#[test]
fn factor_replay_counts_fetch_errors_separately() {
    let mut server = Server::new();

    let _m1 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"fail","blocking_reasons":["no_top_combinations"],"watch_items":[]},"correlation_analysis":{"alert_count":0},"top_combinations":{"items":[]}}}"#)
        .create();

    let _m2 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let req = FactorReplayRequest {
        start_date: "2026-04-01".to_string(),
        end_date: "2026-04-02".to_string(),
        factor_names: vec!["momentum_20".to_string()],
        correlation_threshold: None,
        output: "json".to_string(),
    };

    let out = run_replay(&server.url(), 1000, &req).expect("replay should still succeed");

    assert_eq!(out["summary"]["days"], 2);
    assert_eq!(out["summary"]["error_days"], 1);
    assert_eq!(out["daily_items"][1]["fetch_status"], "error");
    assert_eq!(out["daily_items"][1]["release_gate_status"], "unknown");
}
```

- [x] **Step 3: 运行测试确认 RED**

Run: `cd cli && cargo test --test http_factor_replay`
Expected: FAIL（`factor_replay` 模块/`FactorReplayRequest`/`run_replay` 尚不存在）。

- [x] **Step 4: 提交失败测试**

```bash
git add cli/tests/http_factor_replay.rs
git commit -m "test: add failing tests for factor replay cli aggregation"
```

---

### Task 2: 实现 CLI 命令接线与 replay 编排

**Files:**
- Modify: `cli/Cargo.toml`
- Modify: `cli/src/application/requests.rs`
- Modify: `cli/src/cmd/factor.rs`
- Modify: `cli/src/cmd/mod.rs`
- Modify: `cli/src/application/handlers/mod.rs`
- Create: `cli/src/application/handlers/factor_replay.rs`
- Modify: `cli/src/application/dispatch.rs`

- [x] **Step 1: 增加请求结构与命令枚举**

```rust
// requests.rs
#[derive(Debug, Clone)]
pub struct FactorReplayRequest {
    pub start_date: String,
    pub end_date: String,
    pub factor_names: Vec<String>,
    pub correlation_threshold: Option<f64>,
    pub output: String,
}

pub enum AppCommand {
    // ...existing
    FactorReplay(FactorReplayRequest),
}
```

```rust
// cmd/factor.rs
pub enum FactorSubcommand {
    Optimize(FactorOptimizeArgs),
    Replay(FactorReplayArgs),
}

#[derive(Debug, Args)]
pub struct FactorReplayArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long)]
    pub factors: String,
    #[arg(long)]
    pub correlation_threshold: Option<f64>,
    #[arg(long, default_value = "json")]
    pub output: String,
}
```

- [x] **Step 2: 在 `cmd/mod.rs` 与 `dispatch.rs` 完成路由**

```rust
// cmd/mod.rs
factor::FactorSubcommand::Replay(replay) => AppCommand::FactorReplay(replay.into()),
```

```rust
// dispatch.rs
AppCommand::FactorReplay(args) => factor_replay::handle(args),
```

- [x] **Step 3: 实现 `factor_replay` handler（核心编排）**

```rust
// factor_replay.rs (核心签名)
pub fn run_replay(server_url: &str, timeout_ms: u64, args: &FactorReplayRequest) -> Result<Value, AppError>;
pub fn handle(args: FactorReplayRequest) -> Result<(), AppError>;
```

实现要点：
- 参数校验：`factor_names` 非空，`start_date <= end_date`。
- 用 `chrono::NaiveDate` 生成闭区间日期序列。
- 每日调用 `post_factor_optimize(server_url, day, day, factor_names, correlation_threshold, timeout_ms)`。
- 单日成功：提取 `release_gate.status`、`correlation_analysis.alert_count`、`top_combinations.items[0].factors`。
- 单日失败：写入 `fetch_status=error`、`release_gate_status=unknown`、`error_message`。
- 汇总字段：`days/error_days/pass_days/watch_days/fail_days/avg_alert_count/top1_change_days`。
- 输出：`json` 打印 payload；`table` 调 `render_factor_replay_table`。

- [x] **Step 4: 运行 replay 测试确认 GREEN**

Run: `cd cli && cargo test --test http_factor_replay`
Expected: PASS。

- [x] **Step 5: 提交实现**

```bash
git add cli/Cargo.toml \
  cli/src/application/requests.rs \
  cli/src/cmd/factor.rs cli/src/cmd/mod.rs \
  cli/src/application/handlers/mod.rs cli/src/application/handlers/factor_replay.rs \
  cli/src/application/dispatch.rs \
  cli/tests/http_factor_replay.rs
git commit -m "feat: add hf factor replay command and aggregation flow"
```

---

### Task 3: 实现 table 渲染并补回归测试

**Files:**
- Modify: `cli/src/infrastructure/table_renderer.rs`
- Create: `cli/tests/http_factor_replay_table.rs`

- [x] **Step 1: 写 table 渲染失败测试**

```rust
use hf_cli::infrastructure::table_renderer::render_factor_replay_table;

#[test]
fn factor_replay_table_renders_summary_and_daily_rows() {
    let payload = serde_json::json!({
        "summary": {
            "days": 3,
            "error_days": 1,
            "pass_days": 1,
            "watch_days": 1,
            "fail_days": 0,
            "avg_alert_count": 1.0,
            "top1_change_days": 1
        },
        "daily_items": [
            {"as_of":"2026-04-01","fetch_status":"ok","release_gate_status":"pass","alert_count":0,"top1_factors":["momentum_20","inv_volatility_20"]},
            {"as_of":"2026-04-02","fetch_status":"ok","release_gate_status":"watch","alert_count":2,"top1_factors":["momentum_20","max_drawdown_60"]},
            {"as_of":"2026-04-03","fetch_status":"error","release_gate_status":"unknown","alert_count":0,"top1_factors":[],"error_message":"bad gateway"}
        ]
    });

    let table = render_factor_replay_table(&payload);
    assert!(table.contains("因子回放汇总"));
    assert!(table.contains("逐日回放明细"));
    assert!(table.contains("error_days"));
    assert!(table.contains("release_gate_status"));
    assert!(table.contains("2026-04-03"));
    assert!(table.contains("unknown"));
}
```

- [x] **Step 2: 实现 `render_factor_replay_table`**

```rust
pub fn render_factor_replay_table(payload: &Value) -> String {
    // summary 表 + daily 表
    // daily 列: as_of, fetch_status, release_gate_status, alert_count, top1_factors
}
```

渲染约束：
- `top1_factors` 用 `+` 拼接，如空则显示空串。
- summary 保留关键统计项，便于发布评审截图。

- [x] **Step 3: 运行 table 测试**

Run: `cd cli && cargo test --test http_factor_replay_table`
Expected: PASS。

- [x] **Step 4: 提交渲染能力**

```bash
git add cli/src/infrastructure/table_renderer.rs cli/tests/http_factor_replay_table.rs
git commit -m "feat: add factor replay table rendering"
```

---

### Task 4: 命令级冒烟与全量门禁

**Files:**
- Modify (if needed): `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify (if needed): `AGENTS.md`

- [x] **Step 1: 本地命令冒烟**

Run:
`cd cli && cargo run -- factor replay --start-date 2026-04-01 --end-date 2026-04-03 --factors momentum_20,inv_volatility_20 --output json`

Expected:
- CLI 成功输出 `summary + daily_items` JSON。
- `--output table` 输出包含“因子回放汇总/逐日回放明细”。

- [x] **Step 2: 运行新增测试切片**

Run:
`cd cli && cargo test --test http_factor_replay --test http_factor_replay_table`

Expected: PASS。

- [x] **Step 3: 跑架构与全量门禁**

Run:
- `cd /Users/rongts/strat-flow && make architecture-check`
- `cd /Users/rongts/strat-flow && make check`

Expected: 全部 PASS。

- [x] **Step 4: 文档/上下文收口（如有新增命令示例）**

如更新了文档，至少补充：
- `hf factor replay` 命令示例
- 输出字段与 `release_gate` 解释关系

- [x] **Step 5: 最终提交**

```bash
git add cli/src docs/CLI_OUTPUT_EXAMPLES.md AGENTS.md
git commit -m "feat: integrate factor replay into hf cli"
```

---

## 验收标准（Done）

- `hf factor replay` 命令可用，参数与 `factor optimize` 风格一致。
- 支持 `json/table` 双输出。
- 回放逻辑可区分 `fetch error` 与 `release_gate fail`。
- 新增测试通过，且 `make architecture-check`、`make check` 全绿。

## 自检（Spec Coverage）

- 命令统一入口：Task 2 覆盖。
- 回放聚合逻辑：Task 1/2 覆盖。
- 表格可读输出：Task 3 覆盖。
- 项目门禁与文档收口：Task 4 覆盖。
