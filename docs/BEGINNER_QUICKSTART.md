# HiveFlow 新手使用手册

> 文档目标：给第一次使用 HiveFlow 的同学一份可直接照做的“场景化操作手册”。
> 状态快照日期：2026-04-04

## 1. 第一次启动（按顺序做）

1. 启动数据库
```bash
make db-up
```

1.1 应用迁移（**首次**联调或刚 `git pull` 后出现新的 `quant/db/migrations/*.sql` 时必做）
```bash
make db-migrate
```

2. 启动 quant 服务端
```bash
make run-server
```

3. 配置 CLI（`~/.hiveflow/config.toml`）
```toml
server_url = "http://127.0.0.1:8000"
timeout_ms = 10000
retry = 1
```

4. 验证 CLI 能跑
```bash
cd cli
cargo run -- --help
```

## 2. 场景化上手路径（不要背命令，按场景做）

### 场景 A：今天先确认系统能跑通

你只需要做一件事：跑一天主流水线，看到候选和因子可用性。

```bash
cd cli
cargo run -- pipeline daily --as-of 2026-04-01 --output table
```

看结果时重点关注：
- 候选标的（是否有 Top 候选输出）
- 因子可用性（是否存在明显低可用率告警）

### 场景 B：你要回答“新版本到底有没有更好”

你要做的是区间对比，而不是看某一天。

```bash
cd cli
cargo run -- pipeline compare --start-date 2026-03-01 --end-date 2026-03-30 --top-n 5 --output table
```

看结果时重点关注：
- `top1_symbol_change_days`（两个版本分歧有多频繁）
- Phase2 指标（累计收益、胜率、最大回撤、年化波动率、Sharpe）
- 分组稳定性（industry + market_cap_bucket）

### 场景 C：你要在周会给出“下轮因子组合建议”

这个场景用 `factor optimize`，它是建议态，不会自动改线上。

```bash
cd cli
cargo run -- factor optimize --start-date 2026-01-01 --end-date 2026-04-01 --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60,trend_stability_20,relative_strength_vs_index --output table
```

看结果时重点关注：
- 相关性告警（先看有没有严重冗余）
- Top5 组合推荐（看 `rank=1` 与 `alerts_inside`）
- 方案明细（均衡/收益优先/风险优先）
- `release_gate`（能不能进入下一步评审）

### 场景 D：你怀疑“数据有问题”

先补数据，再查数据，再看明细。

```bash
cd cli
cargo run -- data sync --days 30 --end-date 2026-04-01 --symbols 600519.SH,000001.SZ
cargo run -- task list --days 7 --output table
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table
```

**L1 行情同步是异步任务**（服务端先接单、后台跑；CLI **默认不轮询**，避免长时间卡在 resolving_symbols 等阶段）：

- **默认行为**：`data sync` 提交成功后，终端用中文提示「任务已提交」并给出 **run_id**，stdout 打印受理 JSON；用 **`task progress`**（别名 `task status`）看**当前运行中**的 phase/标的进度，用 **`task list`**（别名 `task sync-runs`）看近期任务列表与终态。
- **在本终端等到结束**：提交时加 **`--wait`**，或事后 **`task progress --run-id <run_id> --watch`**，会显示进度并轮询直到成功/失败/取消等终态。长时间同步请适当增大 `~/.hiveflow/config.toml` 里的 `timeout_ms`，或临时传 `--timeout-ms`。
- **轮询间隔**：`data sync --wait` 与 **`task progress --watch`** 均可用 **`--poll-interval-ms`**（默认约 1500ms）。
- **Ctrl+C**（仅 `--wait` / **`--watch`** 时）：只结束本地轮询，**服务端任务会继续**；终端会提示 `run_id`，可用 **`task progress --run-id <run_id>`** 或 **`task list`** 跟进。
- **已有任务在跑**（HTTP 409）：CLI 会提示当前 `run_id`，可 `cargo run -- task cancel --run-id <run_id>`（或 `data sync-cancel`）取消后再发新同步，或等当前任务结束。
- **部分标的失败**：`cargo run -- task retry-failed --from-run-id <run_id>`（或 `data sync-retry-failed`）默认只提交并返回新 `run_id`；加 **`--wait`** 则在终端等到终态。

排查顺序建议：
- `data sync` 拿 `run_id` 后，用 **`task progress --run-id <run_id>`** 看实时进度，用 **`task list`** 看列表与终态、失败原因摘要（需要阻塞式完成则 **`task progress ... --watch`** 或提交时 **`--wait`**）
- **`task list`** 看最近同步任务；**近窗 K 线**用 **`data query`**（默认 TUI 分页）或 **`data bars`**（显式区间/chart）
- `data bars` 看具体 K 线是否落库

### 场景 E：你想先更新标的池，再跑同步

当你希望先从第三方更新 `csi300/zz500/all_a` 文件，再基于该池拉行情时：

```bash
cd cli
cargo run -- data universe-sync --universe csi300 --provider akshare
cargo run -- data sync --days 30 --end-date 2026-04-01 --universe csi300
```

说明：
- `data universe-sync` 会更新 `quant/config/universes/{universe}.txt`
- `data sync --universe ...` 会按该文件中的股票列表执行同步

## 3. 输出格式怎么选

- `--output table`：人工看结果时优先用它。
- `--output json`：写脚本、做回归、接自动化时用它。
- `task list` 支持 `json|table`（同步任务元数据）；`task progress` 支持 `json|table` 与 **`--watch`**（运行中进度/轮询）；`data query` 支持 `json|tui|table`（K 线窗口查询）。
- `data bars` 支持 `json|table|chart|tui`（K 线明细查询）。

## 4. 常见错误与处理

1. `connection refused` / 请求超时  
先确认 `make run-server` 是否还在运行，以及 `~/.hiveflow/config.toml` 的 `server_url` 是否正确。

2. `INVALID_DATE_RANGE`  
检查 `start_date <= end_date`，格式必须是 `YYYY-MM-DD`。

3. `INVALID_ARGUMENT`  
常见于参数缺失或组合参数冲突（例如不合法的组合大小区间）。

4. 同步报「已有任务在跑」/ HTTP 409  
同一 `timeframe` + 标的集合维度上已有 `running` 任务。用 CLI 提示的 `run_id` 执行 **`hf task cancel --run-id ...`**（或 `data sync-cancel`），或等待该任务结束后再发 `data sync`。

5. 迁移未执行导致同步或查询异常  
确认已执行 `make db-migrate`（见「第一次启动」1.1）。

6. 查询不到数据  
先执行 `data sync`（或确认历史 `run_id` 已成功），再执行 **`task list`** 或 **`data query`** / **`data bars`**。

7. 同步显示 **success** 但 **`error_code: NO_DATA_RETURNED`**  
数据源在该次请求下没有可落库的 bar（分钟线常见原因是 **`--end-date` 与源侧「最近一段」窗口不对齐**）。可换更近的 `end-date`、改用 **日频 `1d`**，或核对标的在 Provider 上是否可查。

8. 联调想「只清行情表」重来  
在已 `db-up` 且已迁移的前提下执行 **`make db-clear-l1`**（破坏性，见根目录 `GETTING_STARTED.md` 4.2），然后**重启** `make run-server`。

9. 参数拼写  
同步与查询使用 **`--timeframe`**，不是 `tmeframe`。

## 5. 当前能力边界

- `factor optimize` 固定是建议态：`advice_only=true`、`decision_weight=0`。
- `pipeline daily` 当前 `execution_plan.orders` 仍为空数组（执行层未进入实盘自动化）。
- L1 行情：`data sync` 为异步任务 + CLI **`--wait` / `task progress --watch`** 轮询；任务元数据用 **`hf task list`**，进度用 **`hf task progress`**；失败标的可用 **`hf task retry-failed`**（或 `data sync-retry-failed`）续跑；无行返回时可能 **`NO_DATA_RETURNED`**；本地清表 **`make db-clear-l1`**。
- L2 因子与 L3 信号（快照/评估等）已在主线可用；更细的层状态见仓库根目录 `AGENTS.md` 表格。

## 6. 深入文档

1. 10 分钟最小闭环（依赖与 `make check`）：[`GETTING_STARTED.md`](../GETTING_STARTED.md)
2. 输出字段合同：[`CLI_OUTPUT_SCHEMA.json`](CLI_OUTPUT_SCHEMA.json)
3. 输出样例：[`CLI_OUTPUT_EXAMPLES.md`](CLI_OUTPUT_EXAMPLES.md)
4. 架构总览：[`ARCHITECTURE.md`](ARCHITECTURE.md)
5. 因子优化细节：[`FACTOR_OPTIMIZATION_P1_USAGE.md`](FACTOR_OPTIMIZATION_P1_USAGE.md)、[`FACTOR_OPTIMIZATION_P2_USAGE.md`](FACTOR_OPTIMIZATION_P2_USAGE.md)
6. L1 异步同步设计（可选）：[`superpowers/specs/2026-04-04-l1-async-sync-design.md`](superpowers/specs/2026-04-04-l1-async-sync-design.md)

## 7. 情景故事：怎么看 `factor optimize --output table`

下面用你这条命令为例：

```bash
cargo run -- factor optimize \
  --start-date 2026-01-01 \
  --end-date 2026-04-01 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60,trend_stability_20,relative_strength_vs_index \
  --output table
```

### 故事 A：周会里快速回答“这期因子还能不能用”

你在周会前跑了这条命令，先看两块：

1. `相关性告警`
- 如果 `alert_count` 很高，说明因子互相太像，信息冗余高。
- 结论通常是：先降权或替换高相关对，不急着上新策略。

2. `Top5 组合推荐`
- 看 `rank=1` 的组合是否稳定（比如连续几周都在前列）。
- 看 `alerts_inside` 是否为空；不为空就说明这组有结构性风险提示。

一句话决策模板：
- “Top1 组合表现最好，但相关性告警偏高，建议继续观察，不直接上线。”

### 故事 B：你看到“预期回撤=0.0000”，怎么解释给团队

在 `方案明细` 里你会看到：
- `方案`（均衡 `balanced` / 收益优先 `return_first` / 风险优先 `risk_first`）
- `预期Sharpe`
- `预期回撤`
- `权重`

这里的“预期回撤”是当前阶段的近似风险分，不是完整交易回测净值回撤。  
所以出现 `0.0000` 并不代表“没有风险”，而是“该窗口下模型没有识别到明显回撤惩罚”。

对外沟通建议：
- “这个值用于方案排序，不用于替代正式回测结论。”

### 故事 C：最终怎么落到行动

跑完表格后，按这个顺序做动作：

1. 看 `release_gate.status`
- `pass`：可进入下一步评审
- `watch`：补材料后再评审
- `fail`：先处理 blocking_reasons

2. 看 `recommended_scheme`
- 作为“下轮实验默认方案”，不是实盘自动生效方案。

3. 记录到实验日志
- 记录时间窗、因子池、Top1 组合、告警数、gate 状态。
- 下次同样窗口复跑，比较推荐是否漂移。

这样你就把一张“难看懂的表”变成了三件事：
- 能不能继续用（健康度）
- 用哪组更稳（方案排序）
- 现在能不能推进（release gate）
