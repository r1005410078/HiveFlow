# HiveFlow 新手入门

HiveFlow 是一个本地运行的投资工具系统。它负责输出确定性的持仓、行情、风险、信号、回测和调仓数据；投资判断放在 `Skill` 中，由 `Codex`、`Claude` 等大模型执行。

## 项目内 / 项目外分层

1. `HiveFlow`
负责确定性工具与 JSON 上下文输出，不做投资判断。

2. `Skill`
负责把分析步骤组织成可复用流程，例如每日检查、策略比较、调仓执行前确认。

3. `Agent Runtime`
由 `Codex`、`Claude` 等外部大模型平台提供，负责执行 Skill、调用 CLI、与用户交互。

项目内真正需要建设的是：

- `HiveFlow`
- `Skill`

## 推荐工作流

当前推荐围绕 3 个 Skill 展开：

| 目标 | 推荐 Skill | 作用 |
|---|---|---|
| 每日检查组合状态 | `hiveflow-daily-check` | 判断今天是否安全、是否需要进一步动作 |
| 比较策略并决定是否切换 | `hiveflow-strategy-selector` | 比较回测与当前市场状态，选策略 |
| 从目标仓位进入执行 | `hiveflow-rebalance-executor` | 生成候选动作，等待用户确认后执行 |

若用户的问题跨阶段，可以使用总控 Skill：`hiveflow-portfolio-advisor`。

Skill 触发条件与路由关系详见：[docs/skills/README.md](/Users/rongts/strat-flow/docs/skills/README.md)

## 你想做什么？

| 我想做什么 | 去哪里 |
|---|---|
| 第一次用，从零开始 | [准备工作](#准备工作) + [场景一：先建立可用上下文](#场景一先建立可用上下文约-10-分钟) |
| 每天检查我的持仓健康 | [场景二：每日检查闭环](#场景二每日检查闭环约-1-分钟) |
| 比较策略并决定是否切换 | [场景三：策略筛选闭环](#场景三策略筛选闭环约-15-分钟) |
| 根据目标仓位准备执行 | [场景四：调仓执行闭环](#场景四调仓执行闭环约-5-分钟) |
| 持续对比实盘和回测 | [场景五：实盘 vs 回测追踪](#场景五实盘-vs-回测追踪持续追踪) |

---

## 准备工作

所有场景都需要先完成这一步。**如果你只想用演示数据体验（场景一），跳过第 2、3 步即可。**

**第 1 步：安装**

在项目根目录执行：

```bash
uv sync
```

验证安装成功：

```bash
uv run hiveflow --help
```

**第 2 步：初始化数据库**（使用真实数据时需要）

```bash
uv run hiveflow bootstrap
```

**第 3 步：连接 OKX 账户**（场景二、五需要）

在项目根目录创建 `.env` 文件，写入你的 OKX API 凭证：

```
HIVEFLOW_OKX_API_KEY=你的key
HIVEFLOW_OKX_API_SECRET=你的secret
HIVEFLOW_OKX_API_PASSPHRASE=你的passphrase
```

> OKX API Key 在 OKX 官网 → 个人中心 → API 管理 中创建。创建时权限选"读取"+"交易"，如需执行调仓则需开启交易权限。

---

## 场景一：先建立可用上下文（约 10 分钟）

> **我想做什么：** 我刚安装好，还没有 OKX API，想先把系统跑通，并给 Agent 一个能用的上下文。

这个场景使用内置演示数据，不需要 OKX 账户，目标是先跑通“数据 -> 上下文 -> 调仓预览”的最小闭环。

**第 1 步：生成演示数据**

```bash
uv run hiveflow init-demo
```

这条命令会自动创建演示策略、持仓、风险信号和目标配置，也会完成数据库初始化。

**第 2 步：诊断环境**

```bash
uv run hiveflow doctor
```

看到所有检查项显示"正常"后继续。

**第 3 步：查看整体状态**

```bash
uv run hiveflow summary
```

你会看到当前持仓、风险信号、目标持仓和最新调仓建议的摘要。

**第 4 步：查看持仓偏离**

```bash
uv run hiveflow positions drift
```

输出示例：

```
持仓偏离分析

  标的    实际权重   目标权重   偏差    等级     建议
  BTC     0.65      0.50      +0.15   high    减仓
  ETH     0.20      0.30      -0.10   medium  加仓
  USDT    0.15      0.20      -0.05   low     观察
```

偏差等级说明：`low` 观察即可，`medium` 考虑调整，`high` 建议尽快操作。

**第 5 步：获取调仓建议**

```bash
uv run hiveflow rebalance preview
```

输出示例：

```
调仓建议

  策略：进攻突破策略（进攻型 · 趋势|动量）

  标的    当前权重   目标权重   建议     风险水位
  BTC     0.65      0.50      sell     medium
  ETH     0.20      0.30      buy      low
  USDT    0.15      0.20      buy      low
```

> 当某个标的风险水位为 `high` 时，`buy` 建议会自动变为 `hold`（风险门控）。

**A 股持仓导入（Agent 友好 JSON）**

推荐使用新命令：

```bash
uv run hiveflow positions template-cn --file ./cn_positions.csv
uv run hiveflow positions import-cn --file ./cn_positions.csv
uv run hiveflow positions import-cn --file ./cn_positions.csv --output json
```

`template-cn` 生成的 CSV 使用中文表头：`代码,数量,市值`（仅支持中文表头导入）。

`--output json` 会返回两部分：
- `result`：本次导入结果（如 `imported`、`file`）
- `agent_template`：给 Agent 的可复用模板（命令模板、CSV 列要求、示例行、校验规则）

旧命令 `positions import-csv` 仍可用，但已标记为弃用，建议迁移到 `import-cn`。

---

## 场景二：每日检查闭环（约 1 分钟）

> **我想做什么：** 我每天花 30 秒确认持仓有没有异常，并让 Agent 判断今天要不要继续动作。

**前提：** 已完成准备工作第 3 步（OKX 已连接）。

**首次使用（只需一次）：先补历史数据**

```bash
uv run hiveflow sync --days 30
```

`check`/`signal` 依赖最近历史价格计算指标，首次建议至少同步 30 天。

**日常流程（建议 4 步）**

```bash
uv run hiveflow sync
uv run hiveflow context daily --output json
uv run hiveflow positions list --output json
# 跨市场总览（新增）
uv run hiveflow portfolio summary --output json
```

推荐让 Agent 执行 `hiveflow-daily-check`，把上面命令串成一份每日结论。

`positions list` 已升级为跨市场折算视图，默认展示：
- `市值(USDT)`
- `市值(CNY)`
- `占比（全局）`

并在表格底部显示总资产合计与本次折算汇率来源（`akshare` 或 `config_fallback`）。

`positions drift` 会**忽略市值 <= 0.01 USDT** 的极小仓位，避免噪声币影响判断。

`check` 输出示例：

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  今日持仓健康检查  2026-03-19
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[结论] ⚠️  建议关注 — ETH 近7日回撤较大

  币种   7日最大回撤   状态
  BTC    -3.2%        正常
  ETH    -12.4%       ⚠️ 注意
  SOL    -8.1%        正常

建议动作
  → ETH 回撤偏大，留意是否触发止损线
```

风险等级说明：

| 7日最大回撤 | 状态 |
|---|---|
| 高于 -10% | 正常 |
| -10% ~ -20% | ⚠️ 注意 |
| 低于 -20% | 🔴 危险 |

`signal snapshot` 输出示例（节选，`--symbol BTC` 时输出 17 个 BTC 指标 + 7 个组合级指标共 24 个信号）：

```json
{
  "symbol": "BTC",
  "snapshot_id": "sig-202603201234560001",
  "feature_set_version": "signal-v1.0",
  "signals": [ ... 24 items ... ],
  "category_metrics": { ... },
  "conflict_matrix": [ ... ]
}
```

**需要单独查看某个资产时**

```bash
uv run hiveflow signal snapshot --symbol BTC --output json
```

**需要看历史对比时**

```bash
uv run hiveflow signal history --output json
uv run hiveflow signal show <id> --output json
uv run hiveflow style backtest-rank --output json
uv run hiveflow style history --output json
uv run hiveflow style show <id> --output json
```

`show` 返回字段与实时命令保持一致（包含 `feature_set_version`、`symbols_hash`、`objective`、`constraints`、`best_candidate` 等），方便 Agent 做可复现分析。

**一条命令给 Agent 喂日常上下文（推荐）**

```bash
uv run hiveflow context daily --output json
# 或输出统一 envelope：
uv run hiveflow context daily --output json --envelope
# 查看 JSON schema：
uv run hiveflow context daily --json-schema
# 严格要求“快照新鲜”（默认 24 小时阈值）：
uv run hiveflow context daily --output json --strict-source fresh --max-age-hours 24
```

该命令会一次性聚合输出 `check + drift + signal_latest + style_latest`，适合作为 Agent 的标准输入。
并额外输出 `source_meta`（来源记录 ID、`as_of`、`age_hours`），便于 Agent 判断上下文时效与可追溯性。
默认输出 `windows.w24/w7/w30`（交易窗口分组），每个窗口都含 `check/drift/signal/style/source_meta`。
也可自定义窗口列表：

```bash
uv run hiveflow context daily --output json --windows 12,24
```

`--windows` 使用逗号分隔正整数，重复窗口会自动去重（按输入顺序保留）。
非法值（如 `0`、`abc`、`24,,7`）会直接返回参数错误（exit code 2）。
并输出 `window_diff`（`signal_diff/style_diff/risk_diff/consensus_score`），便于 Agent 识别短中长窗口分歧。
`summary` 会同时回传 `windows_requested/window_count_requested/window_count_total_computed` 与 `window_keys_success/window_keys_failed/window_status_map`，用于审计本次窗口请求与执行结果。
其中 `window_status_map` 覆盖全部请求窗口（包含失败窗口），可直接做窗口状态快照。
并提供 `is_window_audit_consistent`，用于一键判断窗口审计字段是否一致。
此外新增 `window_audit` 子对象（含上述审计字段），平铺字段继续保留以兼容现有消费方。
`window_audit` 内含 `window_audit_schema_version`（当前 `v1`），便于下游按版本做解析升级。
完整字段定义与示例见：`docs/context/WINDOW_AUDIT_CONTRACT.md`。
若只需要轻量决策上下文（不含窗口多尺度计算），可使用：

```bash
uv run hiveflow context decision --output json
uv run hiveflow context decision --output json --envelope
uv run hiveflow context decision --json-schema
```

`context decision` 输出 `policy + evaluation + execution_plan`，适合 Agent 快速决策路由。
完整字段定义与示例见：`docs/context/DECISION_CONTEXT_CONTRACT.md`。

**跨市场资产总览（Phase 2-C/D 新增）**

当你希望快速看“组合总资产 + 市场分布（crypto/A 股）”时，使用：

```bash
uv run hiveflow portfolio summary
uv run hiveflow portfolio summary --output json
```

`portfolio summary` 会基于持仓货币（`USDT` / `CNY`）统一折算并输出：
- `total_usdt`、`total_cny`
- `fx_rate`、`fx_source`
- `breakdown`（各市场占比与本位币金额）
- `positions`（每个标的的双币市值与全局权重）

如果实时汇率拉取失败，会自动回退到配置项 `HIVEFLOW_CNY_USDT_RATE`（默认 `7.25`）。
可选窗口严格策略：

```bash
# 任一窗口失败即整体失败（默认）
uv run hiveflow context daily --output json --strict-window all

# 允许部分窗口失败，失败窗口写入 summary.window_failures
uv run hiveflow context daily --output json --strict-window partial
```

**严格模式与系统日志（排障）**

当 `signal` / `style` 因数据缺失失败时，命令会返回结构化错误并写入系统日志表（含 `trace_id`）：

```bash
sqlite3 data/hiveflow.db "select id,level,message,trace_id,created_at from systemlog order by id desc limit 10;"
```

**设置自动定时检查（可选）**

```bash
uv run hiveflow perf setup-cron --dry-run    # 预览将写入的定时任务
uv run hiveflow perf setup-cron              # 实际安装
```

---

## 场景三：策略筛选闭环（约 15 分钟）

> **我想做什么：** 我想知道当前市场更适合哪种策略，再决定要不要切换。

**第 1 步：准备行情数据**

先生成 CSV 模板：

```bash
uv run hiveflow market-data template
```

在当前目录生成 `prices.csv`，按模板格式填入历史价格数据（每行一条日线记录），然后导入：

```bash
uv run hiveflow market-data import --file ./prices.csv
uv run hiveflow market-data summary    # 确认导入成功
```

**第 2 步：查看内置策略列表**

```bash
uv run hiveflow quant list
```

系统内置 8 种策略：EqualWeight（等权重）、Momentum（动量）、MeanReversion（均值回归）、MovingAverageCross（均线交叉）、BollingerBand（布林带）、RiskParity（风险平价）、MaxSharpe（最大夏普）、MinVariance（最小方差）。

**第 3 步：快速看一个策略当前权重**

```bash
uv run hiveflow quant run --strategy MomentumStrategy
```

这个命令按当前数据点计算一次权重，输出建议配比，但**不含历史回测**。用来快速理解策略当前偏好。

**第 4 步：运行历史回测**

```bash
uv run hiveflow backtest quant-run --strategy Momentum --rebalance-days 30
```

> 与第 3 步的区别：这里模拟的是**历史上每 30 天重新计算权重并调仓**的完整过程，输出包含权益曲线（资产随时间的涨跌），可以看出策略的历史真实表现。

记下输出的回测 ID（例如 `#3`），后续步骤会用到。

**第 5 步：可视化查看回测结果**

```bash
uv run hiveflow backtest show 3    # 替换 3 为你的回测 ID
```

输出示例：

```
回测 #3 · MomentumStrategy

  总收益    18.5%
  最大回撤  -8.2%    （历史最大亏损幅度）
  Sharpe    1.34     （收益/风险比，越高越好）

  权益曲线（120 期）
  ▁▁▂▂▃▃▄▅▅▆▆▇▇▇█▇▇▆▇▇▇▇▇▇▇▇█▇▇█▇▇▇█

  风险指标
  年化波动率   18.2%
  胜率         61.5%
  Calmar       4.22    （年化收益/最大回撤，越高越好）
```

**第 6 步：多策略并排对比**

跑几个不同策略后，对比它们：

```bash
uv run hiveflow backtest quant-run --strategy EqualWeight --rebalance-days 30
uv run hiveflow backtest quant-run --strategy RiskParity --rebalance-days 30
uv run hiveflow backtest compare 1 2 3    # 替换为你的回测 ID 列表
```

**第 7 步：查看资产风险数据**

```bash
uv run hiveflow risk-analysis assets
```

输出每个资产的年化波动率、历史最大回撤和资产间的相关性（相关性越低，组合分散效果越好）。

推荐让 Agent 执行 `hiveflow-strategy-selector`，把当前 `context daily`、策略列表和回测比较串起来，回答“该不该切换”。

**第 7 步（可选）：将最优配比写入目标持仓**

找到表现最好的回测 ID 后：

```bash
uv run hiveflow targets set-from-backtest 3    # 替换 3 为目标回测 ID
uv run hiveflow rebalance preview              # 查看对应的调仓建议
```

---

## 场景四：调仓执行闭环（约 5 分钟）

> **我想做什么：** 我已经选好了策略或目标仓位，想生成动作计划，但不想跳过确认直接交易。

**前提：** 已完成场景三，或者已经有目标持仓。

**第 1 步：写入目标持仓**

```bash
uv run hiveflow targets set-from-backtest <backtest_id>
```

**第 2 步：查看偏离与调仓建议**

```bash
uv run hiveflow positions drift --output json
uv run hiveflow rebalance preview --output json
```

**第 3 步：让 Agent 生成候选执行计划**

推荐让 Agent 执行 `hiveflow-rebalance-executor`。它应该只生成候选动作，并等待用户确认。

**第 4 步：用户确认后执行**

```bash
uv run hiveflow trade execute --orders '[{"symbol":"ETH","action":"buy","usdt":500}]'
```

> 不推荐跳过预览和确认，直接执行交易。

---

## 场景五：实盘 vs 回测追踪（持续追踪）

> **我想做什么：** 我按量化策略配置了持仓，想持续追踪实盘表现是否跟上回测。

**前提：** 已完成场景三（有回测 ID）、准备工作第 3 步（OKX 已连接）。

**第 1 步：记录第一次持仓快照**

```bash
uv run hiveflow perf snapshot
```

这条命令从 OKX 同步当前持仓市值，并存入本地数据库。

**第 2 步：设置自动定时快照**

创建配置文件 `config/tracking.json`（如果不存在），然后：

```bash
uv run hiveflow perf setup-cron --dry-run    # 预览 cron 任务内容
uv run hiveflow perf setup-cron              # 安装定时任务（默认每小时一次）
```

安装后，系统会每小时自动记录一次持仓快照，无需手动操作。

**第 3 步：查看历史快照**

```bash
uv run hiveflow perf list           # 全部历史
uv run hiveflow perf list --limit 5 # 最近 5 条
```

**第 4 步：对比实盘 vs 回测**

```bash
uv run hiveflow perf compare 3    # 替换 3 为你的回测 ID
```

输出示例：

```
实盘（10 个快照） vs 回测 #3

  实盘 : ▁▂▂▃▄▄▅▅▆▇
  回测 : ▁▂▃▄▅▅▆▇▇█

  指标          实盘       回测
  总收益率      8.00%    18.50%
  年化收益率   32.10%    55.30%
  最大回撤     -2.50%    -8.20%
```

实盘收益低于回测是正常现象（回测不含手续费、滑点和市场冲击），关注的重点是**趋势方向是否一致**。

---

## 遇到问题？

**环境诊断**

```bash
uv run hiveflow doctor
```

**查看命令完整参数**

```bash
uv run hiveflow <命令> --help

# 例如：
uv run hiveflow backtest quant-run --help
uv run hiveflow quant blend create --help
```

**常见报错**

| 报错现象 | 解决方法 |
|---|---|
| 找不到 `hiveflow` 命令 | 执行 `uv sync` 重新安装依赖 |
| 数据库为空 / 无数据 | 执行 `uv run hiveflow init-demo` 生成演示数据 |
| OKX API 连接失败 | 检查 `.env` 三个 key 是否填写正确；确认 OKX 后台 API 已启用且未设置 IP 白名单限制 |
| 回测结果为空 | 确认已用 `market-data import` 导入行情数据 |

**获取 JSON 输出**（给脚本或 AI 消费）

所有命令均支持 `--output json`：

```bash
uv run hiveflow summary --output json
uv run hiveflow rebalance preview --output json
uv run hiveflow backtest show 3 --output json
```
