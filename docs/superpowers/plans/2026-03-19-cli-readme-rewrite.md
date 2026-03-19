# CLI README 新手文档重写 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `docs/cli/README.md` 重写为以用户故事为骨架的新手入门文档，替换现有 1029 行命令参考文档。

**Architecture:** 首页导航表（锚点链接）+ 五个独立场景章节 + 附录。每个场景以用户故事开头，步骤可直接复制执行，关键命令含预期输出示例。

**Tech Stack:** Markdown，无代码改动，仅文档重写。

**Spec:** `docs/superpowers/specs/2026-03-18-cli-readme-redesign.md`

---

## Chunk 1: 文档骨架 + 准备工作

### Task 1: 新建文档，写入首页导航与准备工作

**Files:**
- Modify: `docs/cli/README.md`（全量替换）

- [ ] **Step 1: 备份现有文档**

```bash
cp docs/cli/README.md docs/cli/README.old.md
```

- [ ] **Step 2: 写入文档标题、首页导航表**

内容如下（完整写入，不省略）：

```markdown
# HiveFlow 新手入门

HiveFlow 是一个本地运行的加密资产组合管理工具，帮你追踪持仓健康、运行量化策略、对比回测与实盘表现。

## 你想做什么？

| 我想做什么 | 去哪里 |
|---|---|
| 第一次用，从零开始 | [场景一：从零到第一份调仓建议](#场景一从零到第一份调仓建议约-10-分钟) |
| 每天检查我的持仓健康 | [场景二：每日持仓健康检查](#场景二每日持仓健康检查约-1-分钟) |
| 跑量化回测，找最优配置 | [场景三：量化回测——找历史最优策略](#场景三量化回测找历史最优策略约-15-分钟) |
| 混合多个策略，自动优化权重 | [场景四：多策略混合优化](#场景四多策略混合优化约-5-分钟) |
| 对比实盘和回测的差距 | [场景五：实盘 vs 回测对比](#场景五实盘-vs-回测对比持续追踪) |
```

- [ ] **Step 3: 写入准备工作章节**

```markdown
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
```

- [ ] **Step 4: 提交**

```bash
git add docs/cli/README.md docs/cli/README.old.md
git commit -m "docs: 新手文档骨架 + 准备工作章节"
```

---

## Chunk 2: 场景一 + 场景二

### Task 2: 写入场景一（演示数据体验）

**Files:**
- Modify: `docs/cli/README.md`

- [ ] **Step 1: 写入场景一章节**

```markdown
---

## 场景一：从零到第一份调仓建议（约 10 分钟）

> **我想做什么：** 我刚安装好，还没有 OKX API，想先看看系统能给我什么建议。

这个场景使用内置演示数据，不需要 OKX 账户，可以完整体验从持仓到调仓建议的全流程。

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
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli/README.md
git commit -m "docs: 新手文档场景一（演示数据体验）"
```

### Task 3: 写入场景二（每日健康检查）

**Files:**
- Modify: `docs/cli/README.md`

- [ ] **Step 1: 写入场景二章节**

```markdown
---

## 场景二：每日持仓健康检查（约 1 分钟）

> **我想做什么：** 我每天花 30 秒确认持仓有没有异常，有风险立刻看到。

**前提：** 已完成准备工作第 3 步（OKX 已连接）。

**日常两步流程：**

```bash
uv run hiveflow sync     # 同步最新持仓和价格（约 5 秒）
uv run hiveflow check    # 输出风险结论
```

输出示例：

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

**首次使用：同步历史数据**

第一次运行时，需要同步历史 K 线才能计算回撤指标：

```bash
uv run hiveflow sync --days 30    # 同步最近 30 天
uv run hiveflow check
```

**设置自动定时检查**

不想每天手动跑？可以设置 cron 自动执行：

```bash
uv run hiveflow perf setup-cron --dry-run    # 预览将写入的定时任务
uv run hiveflow perf setup-cron              # 实际安装
```
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli/README.md
git commit -m "docs: 新手文档场景二（每日健康检查）"
```

---

## Chunk 3: 场景三 + 场景四

### Task 4: 写入场景三（量化回测）

**Files:**
- Modify: `docs/cli/README.md`

- [ ] **Step 1: 写入场景三章节**

```markdown
---

## 场景三：量化回测——找历史最优策略（约 15 分钟）

> **我想做什么：** 我想知道哪种量化策略过去表现最好，再决定用哪个。

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

**第 3 步：快速看一个策略的配比建议**

```bash
uv run hiveflow quant run --strategy Momentum
```

这个命令按当前数据点计算一次权重，输出建议配比，但**不含历史回测**。用来快速了解策略逻辑。

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

**第 7 步：查看资产风险分析**

```bash
uv run hiveflow risk-analysis assets
```

输出每个资产的年化波动率、历史最大回撤和资产间的相关性（相关性越低，组合分散效果越好）。

**第 8 步（可选）：将最优配比写入目标持仓**

找到表现最好的回测 ID 后：

```bash
uv run hiveflow targets set-from-backtest 3    # 替换 3 为目标回测 ID
uv run hiveflow rebalance preview              # 查看对应的调仓建议
```
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli/README.md
git commit -m "docs: 新手文档场景三（量化回测）"
```

### Task 5: 写入场景四（多策略混合）

**Files:**
- Modify: `docs/cli/README.md`

- [ ] **Step 1: 写入场景四章节**

```markdown
---

## 场景四：多策略混合优化（约 5 分钟）

> **我想做什么：** 我觉得单一策略风险太集中，想把几个策略组合起来，让系统自动分配权重。

**前提：** 已完成场景三（至少跑过几次回测，有历史数据）。

**第 1 步：创建多策略混合（自动权重）**

```bash
uv run hiveflow quant blend create my_blend \
  --strategies MomentumStrategy,EqualWeightStrategy,RiskParityStrategy
```

不传 `--weights` 时，系统自动按各策略的夏普比率（Sharpe ratio，收益/风险比）归一化计算权重。

**第 2 步：运行混合策略，查看结果**

```bash
uv run hiveflow quant blend run my_blend
```

输出示例：

```
Blend 'my_blend' 资产权重

  资产    权重
  BTC    0.4200
  ETH    0.3100
  SOL    0.1800
  BNB    0.0900
```

**第 3 步：查看混合详情**

```bash
uv run hiveflow quant blend show my_blend
```

**第 4 步（可选）：直接写入目标持仓**

```bash
uv run hiveflow quant blend run my_blend --apply
```

**其他常用操作：**

手动指定权重（权重数量必须和策略数量一致）：

```bash
uv run hiveflow quant blend create manual_blend \
  --strategies MomentumStrategy,EqualWeightStrategy \
  --weights 0.7,0.3
```

按 Calmar ratio（年化收益/最大回撤）优化权重：

```bash
uv run hiveflow quant blend create calmar_blend \
  --strategies MomentumStrategy,EqualWeightStrategy,RiskParityStrategy \
  --optimize-metric calmar
```

修改已有 blend：

```bash
uv run hiveflow quant blend update my_blend \
  --strategies MomentumStrategy,EqualWeightStrategy \
  --weights 0.6,0.4
```
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli/README.md
git commit -m "docs: 新手文档场景四（多策略混合）"
```

---

## Chunk 4: 场景五 + 附录 + 收尾

### Task 6: 写入场景五（实盘追踪）

**Files:**
- Modify: `docs/cli/README.md`

- [ ] **Step 1: 写入场景五章节**

```markdown
---

## 场景五：实盘 vs 回测对比（持续追踪）

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
```

- [ ] **Step 2: 提交**

```bash
git add docs/cli/README.md
git commit -m "docs: 新手文档场景五（实盘 vs 回测追踪）"
```

### Task 7: 写入附录 + 最终清理

**Files:**
- Modify: `docs/cli/README.md`
- Delete: `docs/cli/README.old.md`（确认无需保留后删除）

- [ ] **Step 1: 写入附录章节**

```markdown
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
```

- [ ] **Step 2: 确认文档完整性**

检查：
- 首页导航表的锚点链接是否与各章节标题完全对应
- 每个场景都有用户故事一句话
- 每个步骤的命令都带 `uv run hiveflow` 前缀
- 输出示例覆盖场景一、二、三、四、五

- [ ] **Step 3: 删除备份文件**

```bash
rm docs/cli/README.old.md
```

- [ ] **Step 4: 最终提交**

```bash
git add docs/cli/README.md
git rm docs/cli/README.old.md
git commit -m "docs: CLI README 新手入门文档完成"
```
