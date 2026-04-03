# HiveFlow 新手使用手册

> 文档目标：给第一次使用 HiveFlow 的同学一份可直接照做的“场景化操作手册”。
> 状态快照日期：2026-04-03

## 1. 第一次启动（按顺序做）

1. 启动数据库
```bash
make db-up
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
cargo run -- data query --days 7 --output table
cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table
```

排查顺序建议：
- `data sync` 看是否写入成功
- `data query` 看最近任务状态与错误信息
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
- `data query`、`data bars` 支持 `chart`，`data bars` 还支持 `tui`。

## 4. 常见错误与处理

1. `connection refused` / 请求超时  
先确认 `make run-server` 是否还在运行，以及 `~/.hiveflow/config.toml` 的 `server_url` 是否正确。

2. `INVALID_DATE_RANGE`  
检查 `start_date <= end_date`，格式必须是 `YYYY-MM-DD`。

3. `INVALID_ARGUMENT`  
常见于参数缺失或组合参数冲突（例如不合法的组合大小区间）。

4. 查询不到数据  
先执行 `hf data sync`，再执行 `hf data query` 或 `hf data bars`。

## 5. 当前能力边界

- `factor optimize` 固定是建议态：`advice_only=true`、`decision_weight=0`。
- `pipeline daily` 当前 `execution_plan.orders` 仍为空数组（执行层未进入实盘自动化）。
- 目前主线是 L2 能力已可用，L3 信号工程是后续阶段。

## 6. 深入文档

1. 输出字段合同：[`CLI_OUTPUT_SCHEMA.json`](CLI_OUTPUT_SCHEMA.json)
2. 输出样例：[`CLI_OUTPUT_EXAMPLES.md`](CLI_OUTPUT_EXAMPLES.md)
3. 架构总览：[`ARCHITECTURE.md`](ARCHITECTURE.md)
4. 因子优化细节：[`FACTOR_OPTIMIZATION_P1_USAGE.md`](FACTOR_OPTIMIZATION_P1_USAGE.md)、[`FACTOR_OPTIMIZATION_P2_USAGE.md`](FACTOR_OPTIMIZATION_P2_USAGE.md)

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
