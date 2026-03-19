# CLI README 重写设计文档

## 背景与目标

**问题**：现有 `docs/cli/README.md`（1029 行）以命令为轴组织，读起来像 man page，新手无法判断从哪里开始。

**目标**：面向零基础用户，以用户故事为骨架，重写为新手入门文档。

## 约束条件

- 语言：中文
- 参数说明：保留关键参数，不求全（详细参数靠 `--help`）
- 目标读者：有加密资产持仓、会用命令行的普通用户（不懂量化）
- 核心场景：实盘健康检查（日常用）+ 量化回测研究（研究型）

## 文档结构

### 首页导航
一句话说明每个场景的适用人群，让用户 5 秒找到自己的入口。

| 我想做什么 | 去哪里 |
|---|---|
| 第一次用，从零开始 | 场景一 |
| 每天检查我的持仓健康 | 场景二 |
| 跑量化回测，找最优配置 | 场景三 |
| 混合多个策略，自动优化权重 | 场景四 |
| 对比实盘和回测的差距 | 场景五 |

### 准备工作（所有场景共用）

内容：
1. 安装（`uv sync`）
2. 初始化数据库（`bootstrap`）— 仅在使用**真实数据**时需要；若使用演示数据（场景一），`init-demo` 会自动完成初始化，无需单独执行 `bootstrap`
3. 连接 OKX（创建 `.env`，写入以下三个 key）：
   ```
   HIVEFLOW_OKX_API_KEY=你的key
   HIVEFLOW_OKX_API_SECRET=你的secret
   HIVEFLOW_OKX_API_PASSPHRASE=你的passphrase
   ```
   场景一（演示数据）不需要此步骤。

风格：步骤编号 + 可复制命令，不解释底层原理。

### 场景一：从零到第一份调仓建议（~10 分钟）

**用户故事**：我刚安装好，没有 OKX API，想先看看系统能给我什么。

步骤流程（命令均以 `uv run hiveflow` 开头）：
1. `uv run hiveflow init-demo` — 一键生成演示数据
2. `uv run hiveflow doctor` — 确认系统正常
3. `uv run hiveflow summary` — 查看整体状态摘要
4. `uv run hiveflow positions drift` — 看哪些持仓偏离了目标
5. `uv run hiveflow rebalance preview` — 获取调仓建议

输出示例：展示 `rebalance preview` 的终端截图风格文本。

### 场景二：每日持仓健康检查（~1 分钟）

**用户故事**：我每天花 30 秒确认持仓有没有异常，有风险立刻看到。

前提：已完成准备工作（OKX 已连接）。

步骤流程：
```bash
uv run hiveflow sync      # 同步最新持仓和价格
uv run hiveflow check     # 输出风险结论
```

关键参数说明：
- `sync --days 30`：首次使用时同步历史数据（用于计算回撤）
- `check --output json`：给脚本/AI 消费

输出示例：展示带风险等级的 `check` 输出。

### 场景三：量化回测 — 找历史最优策略（~15 分钟）

**用户故事**：我想知道哪种量化策略过去表现最好，再决定用哪个。

步骤流程（命令均以 `uv run hiveflow` 开头）：
1. 准备行情数据（`uv run hiveflow market-data template` → 填写 CSV → `uv run hiveflow market-data import --file ./prices.csv`）
2. 查看内置策略（`uv run hiveflow quant list`）
3. 快速预算权重（`uv run hiveflow quant run --strategy Momentum`）— 不含时间序列，仅按当前数据点计算一次权重，用于了解策略逻辑
4. 动态再平衡回测（`uv run hiveflow backtest quant-run --strategy Momentum --rebalance-days 30`）— 模拟历史每 N 天重新计算权重并调仓，输出完整权益曲线；步骤 3 和步骤 4 的区别：一个是快照，一个是历史模拟
5. 可视化比较（`uv run hiveflow backtest show <id>`，然后 `uv run hiveflow backtest compare 1 2 3`）— `id` 来自步骤 4 的输出
6. 查看风险指标（`uv run hiveflow risk-analysis assets`）
7. （可选）将最优配比写入目标（`uv run hiveflow targets set-from-backtest <backtest_id>`）— `backtest_id` 是步骤 4/5 中看到的回测编号

输出示例：展示 `backtest show` 的 Sparkline 输出（从现有 README 的 3.0.6 示例提取）。

### 场景四：多策略混合优化（~5 分钟）

**用户故事**：我觉得单一策略风险太集中，想把几个策略组合起来。

步骤流程（命令均以 `uv run hiveflow` 开头）：
1. 创建 blend（自动权重）：`uv run hiveflow quant blend create my_blend --strategies MomentumStrategy,EqualWeightStrategy,RiskParityStrategy`
2. 运行：`uv run hiveflow quant blend run my_blend`
3. 查看结果：`uv run hiveflow quant blend show my_blend`
4. 写入目标：`uv run hiveflow quant blend run my_blend --apply`

关键参数说明：
- `--weights 0.7,0.3`：手动指定权重（策略数量与权重数量必须一致）
- `--optimize-metric calmar`：按 Calmar ratio 自动分配权重（默认为 sharpe）

输出示例：展示 `quant blend run` 的资产权重表格（从现有 README 的 3.0.8 示例提取）。

### 场景五：实盘 vs 回测对比（持续追踪）

**用户故事**：我的量化策略跑了一段时间，想看实盘表现是否跟上回测。

步骤流程：
1. 记录第一次快照：`uv run hiveflow perf snapshot`
2. 设置自动定时快照：
   - 前提：创建 `config/tracking.json`（内容指定定时频率，参考 `--dry-run` 输出）
   - 预览将写入的 cron 行：`uv run hiveflow perf setup-cron --dry-run`
   - 实际安装：`uv run hiveflow perf setup-cron`
3. 随时对比：`uv run hiveflow perf compare <backtest_id>`（`backtest_id` 来自场景三中的回测编号）

输出示例：展示 `perf compare` 的并排 Sparkline + 指标对比表（从现有 README 的 3.0.9 示例提取）。

### 附录：遇到问题？

内容：
- `uv run hiveflow doctor` — 环境诊断
- `uv run hiveflow <命令> --help` — 查看完整参数
- 常见报错：
  - 找不到命令 → `uv sync` 重新安装
  - 数据库为空 / 无数据 → `uv run hiveflow init-demo`
  - OKX API 连接失败 → 检查 `.env` 三个 key 是否正确，确认 OKX 后台已开启 API 权限且未做 IP 限制

## 写作规范

- 每个场景开头必须有**用户故事**（一句话：我想…）
- 步骤用编号，命令用代码块，可直接复制，命令统一用 `uv run hiveflow` 前缀
- 输出示例放在步骤之后（让用户知道"我应该看到什么"）
- 不解释底层架构（Clean Architecture、SQLModel、envelope 等技术词汇）
- 量化指标（Sharpe ratio、Calmar ratio、最大回撤）在**首次出现时**加括号中文解释，后续可直接使用
- 每个场景标注大概耗时，降低新手心理门槛
- 首页导航表格使用 Markdown 锚点链接，让用户可点击直达场景

## 不包含的内容

- 所有 `--flag` 的完整参数说明（用 `--help` 代替）
- 架构解释（命令名来源、层次结构）
- 开发者内容（测试、lint、代码结构）
- 旧命令废弃说明
