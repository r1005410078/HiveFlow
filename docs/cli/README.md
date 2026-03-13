# HiveFlow 命令行使用文档

这份文档用于快速上手 HiveFlow 的命令行能力。

## 0. 命令来源说明（为什么你会觉得陌生）

你看到的 `bootstrap / log / summary` 是第一版地基命令，不是最终产品信息架构里的“页面名称”。

它们来自我们当前的工程化落地步骤：

- 产品文档定义“要解决的问题和能力边界”
- 开发计划把这些能力先落成最小可运行 CLI
- 所以命令名偏工程启动语义，而不是最终用户语义

当前对应关系：

- `bootstrap`：对应“初始化真实状态层和基础策略席位”
- `log`：对应“决策日志（记忆层）”
- `summary`：对应“统一状态摘要（后续会演进成完整决策总览）”

后续我们可以在不改底层能力的前提下，把命令名逐步调整为更贴近业务语言的形式。

## 1. 环境准备

在项目根目录执行：

```bash
uv sync
```

## 2. 查看帮助

```bash
uv run hiveflow --help
```

查看某个子命令帮助：

```bash
uv run hiveflow log --help
```

查看某个命令的 JSON schema（给 AI/Skills 对接）：

```bash
uv run hiveflow summary --json-schema
```

如果你希望 JSON 输出带统一包装层（包含 `schema_version` 和 `command`）：

```bash
uv run hiveflow summary --output json --envelope
```

主题切换（仅 pretty 输出生效）：

```bash
uv run hiveflow summary --theme hacker
uv run hiveflow summary --theme minimal
```

### 2.1 命令帮助速查（建议收藏）

```bash
# 根命令帮助（所有一级命令）
uv run hiveflow --help

# 某个命令组帮助（查看二级命令）
uv run hiveflow positions --help
uv run hiveflow targets --help
uv run hiveflow current --help

# 某个具体动作帮助（查看参数）
uv run hiveflow positions drift --help
uv run hiveflow current run --help
uv run hiveflow targets template-rollback --help

# 给 AI/Skills 的结构说明
uv run hiveflow rebalance preview --json-schema
```

## 3. 核心命令

### 3.0 快速跑通（推荐）

```bash
uv run hiveflow init-demo
uv run hiveflow doctor
uv run hiveflow summary
```

作用：

- `init-demo`：一键生成演示数据（策略/持仓/风险/目标/建议）
- `doctor`：检查数据库、模板配置和基础数据状态

### 3.0.1 常用 Example（可直接复制）

```bash
# Example 1: 快速演示闭环
uv run hiveflow init-demo
uv run hiveflow current run
uv run hiveflow positions drift

# Example 2: 查看可给模型消费的 JSON（带统一 envelope）
uv run hiveflow summary --output json --envelope
uv run hiveflow rebalance preview --output json --envelope

# Example 3: 模板误改后回滚
uv run hiveflow targets template-set --scope dimension --key "趋势|动量" --weights "BTC=0.7,ETH=0.2,USDT=0.1"
uv run hiveflow targets template-rollback

# Example 4: 只看某个策略的偏离与建议
uv run hiveflow current set-strategy --name "进攻突破策略"
uv run hiveflow positions drift --strategy "进攻突破策略"
uv run hiveflow rebalance preview --strategy "进攻突破策略"
```

### 3.0.2 行情契约与回测 Example

```bash
# 1) 生成行情模板并填写
uv run hiveflow market-data template

# 2) 校验行情文件是否符合契约
uv run hiveflow market-data validate --file ./prices.csv

# 3) 导入行情到本地数据库（可查询）
uv run hiveflow market-data import --file ./prices.csv --mode replace
uv run hiveflow market-data summary
uv run hiveflow market-data list --symbol BTC

# 4) 运行一次策略回测
uv run hiveflow backtest run --strategy "进攻突破策略" --file ./prices.csv

# 5) 查看回测历史
uv run hiveflow backtest list --strategy "进攻突破策略"
```

说明：
- 当前回测命令仍使用 `--file` 读取行情文件。
- `market-data import/list/summary` 用于把行情沉淀进系统并方便日常核对。

### 3.0.3 回测进阶 Example（参数版）

```bash
# Example A: 带手续费和滑点做更接近真实交易的回测
uv run hiveflow backtest run \
  --strategy "进攻突破策略" \
  --file ./prices.csv \
  --fee-bps 5 \
  --slippage-bps 3
```

```bash
# Example B: 输出 JSON（给脚本 / AI 继续处理）
uv run hiveflow backtest run \
  --strategy "进攻突破策略" \
  --file ./prices.csv \
  --fee-bps 5 \
  --slippage-bps 3 \
  --output json
```

```bash
# Example C: 连续跑多次参数，最后按策略查看历史结果
uv run hiveflow backtest run --strategy "进攻突破策略" --file ./prices.csv --fee-bps 2 --slippage-bps 1
uv run hiveflow backtest run --strategy "进攻突破策略" --file ./prices.csv --fee-bps 5 --slippage-bps 3
uv run hiveflow backtest run --strategy "进攻突破策略" --file ./prices.csv --fee-bps 8 --slippage-bps 5
uv run hiveflow backtest list --strategy "进攻突破策略"
```

```bash
# Example D: 只取历史回测结果的结构化输出
uv run hiveflow backtest list --strategy "进攻突破策略" --output json
```

### 3.1 初始化本地数据库与基础数据

```bash
uv run hiveflow bootstrap
```

作用：

- 创建数据表
- 写入默认策略席位（进攻/防守/长期）
- 写入默认策略类型对应的基础策略

### 3.2 写入决策日志

```bash
uv run hiveflow log --summary "减仓 BTC 5%" --decision-type "rebalance" --notes "风险水位升高"
```

参数说明：

- `--summary`：决策摘要（必填）
- `--decision-type`：决策类型（必填）
- `--notes`：补充备注（可选）

### 3.3 查看决策日志列表

```bash
uv run hiveflow logs list
```

可选参数：

- `--limit`：最多返回条数（默认 100）
- `--output json`：输出结构化日志，便于脚本/模型读取
- `--theme minimal`：切换为简洁展示

JSON 输出示例：

```bash
uv run hiveflow logs list --output json
```

### 3.4 导出决策日志 CSV

```bash
uv run hiveflow logs export --file ./decision-logs.csv
```

可选参数：

- `--limit`：最多导出条数（默认 1000）
- `--output json`：返回导出结果（文件路径、导出条数）

### 3.5 查看系统摘要（当前为最小可行版本演示输出）

```bash
uv run hiveflow summary
```

说明：

- 现在会读取数据库里的真实数据（持仓、风险、目标、调仓建议、决策日志）
- 支持 JSON 输出（给脚本/大模型使用）：

```bash
uv run hiveflow summary --output json
```

### 3.6 新增持仓

```bash
uv run hiveflow positions add --symbol "BTC" --quantity 1.5 --market-value 120000 --weight 0.6
```

参数说明：

- `--symbol`：标的代码（如 BTC / ETH / AAPL）
- `--quantity`：持仓数量
- `--market-value`：当前持仓市值
- `--weight`：持仓权重（0~1）

### 3.7 查看持仓列表

```bash
uv run hiveflow positions list
```

JSON 输出示例：

```bash
uv run hiveflow positions list --output json
```

主题切换示例：

```bash
uv run hiveflow positions list --theme minimal
```

### 3.7.1 查看持仓偏离（M2）

```bash
uv run hiveflow positions drift
```

说明：

- 默认按“当前策略”对比目标持仓
- 输出每个标的的 `actual_weight/target_weight/delta/drift_level/action`
- `drift_level` 分为 `low / medium / high`

JSON 输出示例：

```bash
uv run hiveflow positions drift --output json
```

### 3.8 从 CSV 导入持仓

```bash
uv run hiveflow positions import --file ./positions.csv
```

说明：导入成功后会自动写入一条 `decision_logs` 记录（类型：`positions-import`）。

可选参数：

- `--mode append`：追加导入（默认）
- `--mode replace`：清空旧持仓后导入
- `--output json`：输出结构化导入结果

CSV 列要求（必须包含）：

- `symbol`
- `quantity`
- `market_value`
- `weight`

CSV 示例：

```csv
symbol,quantity,market_value,weight
BTC,1.5,120000,0.6
ETH,2,20000,0.2
```

### 3.9 下载（生成）CSV 模板

```bash
uv run hiveflow positions template
```

默认会在当前目录生成 `positions.csv`。  
也可以指定路径：

```bash
uv run hiveflow positions template --file ./data/positions.csv
```

JSON 输出示例：

```bash
uv run hiveflow positions template --output json
```

### 3.10 查看风险信号列表

```bash
uv run hiveflow risk list
```

JSON 输出示例：

```bash
uv run hiveflow risk list --output json
```

主题切换示例：

```bash
uv run hiveflow risk list --theme minimal
```

### 3.11 从 CSV 导入风险信号

```bash
uv run hiveflow risk import --file ./risk-signals.csv
```

说明：导入成功后会自动写入一条 `decision_logs` 记录（类型：`risk-import`）。

可选参数：

- `--mode append`：追加导入（默认）
- `--mode replace`：清空旧风险信号后导入
- `--output json`：输出结构化导入结果

CSV 列要求（必须包含）：

- `symbol`
- `waterline`
- `score`
- `note`

CSV 示例：

```csv
symbol,waterline,score,note
BTC,high,0.82,波动放大且接近阻力位
ETH,medium,0.55,短期震荡
```

### 3.12 下载（生成）风险 CSV 模板

```bash
uv run hiveflow risk template
```

默认会在当前目录生成 `risk-signals.csv`。  
也可以指定路径：

```bash
uv run hiveflow risk template --file ./data/risk-signals.csv
```

JSON 输出示例：

```bash
uv run hiveflow risk template --output json
```

### 3.13 查看策略列表

```bash
uv run hiveflow strategies list
```

JSON 输出示例：

```bash
uv run hiveflow strategies list --output json
```

主题切换示例：

```bash
uv run hiveflow strategies list --theme minimal
```

### 3.14 从 CSV 导入策略

```bash
uv run hiveflow strategies import --file ./strategies.csv
```

说明：导入成功后会自动写入一条 `decision_logs` 记录（类型：`strategies-import`）。

可选参数：

- `--mode append`：追加导入（默认）
- `--mode replace`：清空旧策略后导入
- `--output json`：输出结构化导入结果

CSV 列要求（必须包含）：

- `name`
- `strategy_type`（或 `category`）
- `thesis`
- `dimension`（可选，支持如 `趋势|动量`）
- `market_regime`
- `backtest_summary`

### 3.15 下载（生成）策略 CSV 模板

```bash
uv run hiveflow strategies template
```

默认会在当前目录生成 `strategies.csv`。  
也可以指定路径：

```bash
uv run hiveflow strategies template --file ./data/strategies.csv
```

JSON 输出示例：

```bash
uv run hiveflow strategies template --output json
```

### 3.16 查看当前策略

```bash
uv run hiveflow current show
```

JSON 输出示例：

```bash
uv run hiveflow current show --output json
```

### 3.17 设置当前策略

```bash
uv run hiveflow current set-strategy --name "进攻突破策略"
```

说明：设置成功后会自动写入一条 `decision_logs` 记录（类型：`current-strategy-set`）。

JSON 输出示例：

```bash
uv run hiveflow current set-strategy --name "进攻突破策略" --output json
```

### 3.17.1 一键执行当前策略（M2/M3）

```bash
uv run hiveflow current run
```

说明：

- 会串联执行：`targets generate` + `rebalance preview`
- 默认保存建议（可用 `--no-save` 关闭）

JSON 输出示例：

```bash
uv run hiveflow current run --output json
```

### 3.18 查看策略席位列表

```bash
uv run hiveflow slots list
```

JSON 输出示例：

```bash
uv run hiveflow slots list --output json
```

### 3.19 更新席位权重

```bash
uv run hiveflow slots set-weight --name "进攻席位" --weight 0.55
```

说明：更新成功后会自动写入一条 `decision_logs` 记录（类型：`slots-set-weight`）。

JSON 输出示例：

```bash
uv run hiveflow slots set-weight --name "进攻席位" --weight 0.55 --output json
```

### 3.20 查看目标持仓列表

```bash
uv run hiveflow targets list
```

说明：列表会同时展示策略名称、策略类型、策略维度、标的与目标权重。

按策略过滤：

```bash
uv run hiveflow targets list --strategy "进攻突破策略"
```

JSON 输出示例：

```bash
uv run hiveflow targets list --output json
```

主题切换示例：

```bash
uv run hiveflow targets list --theme minimal
```

### 3.21 从 CSV 导入目标持仓

```bash
uv run hiveflow targets import --file ./target-allocations.csv
```

说明：导入成功后会自动写入一条 `decision_logs` 记录（类型：`targets-import`）。
同策略同标的在导入时会自动覆盖旧值，避免重复累积。

可选参数：

- `--mode append`：追加导入（默认）
- `--mode replace`：清空旧目标持仓后导入
- `--output json`：输出结构化导入结果

CSV 列要求（必须包含）：

- `strategy_name`
- `symbol`
- `target_weight`

CSV 示例：

```csv
strategy_name,symbol,target_weight
进攻型默认策略,BTC,0.50
进攻型默认策略,ETH,0.30
进攻型默认策略,USDT,0.20
```

### 3.22 下载（生成）目标持仓 CSV 模板

```bash
uv run hiveflow targets template
```

默认会在当前目录生成 `target-allocations.csv`。  
也可以指定路径：

```bash
uv run hiveflow targets template --file ./data/target-allocations.csv
```

JSON 输出示例：

```bash
uv run hiveflow targets template --output json
```

### 3.23 查看目标模板配置

```bash
uv run hiveflow targets template-show
```

JSON 输出示例：

```bash
uv run hiveflow targets template-show --output json
```

### 3.24 设置单条目标模板

```bash
uv run hiveflow targets template-set --scope dimension --key "趋势|动量" --weights "BTC=0.7,ETH=0.2,USDT=0.1"
```

说明：更新成功后会自动写入一条 `decision_logs` 记录（类型：`targets-template-set`）。

JSON 输出示例：

```bash
uv run hiveflow targets template-set --scope type --key "进攻型" --weights "BTC=0.5,ETH=0.3,USDT=0.2" --output json
```

### 3.24.1 回滚目标模板（M2）

```bash
uv run hiveflow targets template-rollback
```

回滚到指定版本：

```bash
uv run hiveflow targets template-rollback --version 2
```

JSON 输出示例：

```bash
uv run hiveflow targets template-rollback --output json
```

### 3.25 基于策略自动生成目标持仓

```bash
uv run hiveflow targets generate --strategy "进攻突破策略"
```

说明：会按策略类型自动套用默认权重模板，并覆盖该策略已有目标持仓。  
如果不传 `--strategy`，会自动使用当前策略（`hiveflow current show` 的值）。  
导入成功后会自动写入一条 `decision_logs` 记录（类型：`targets-generate`）。

说明补充：当策略维度匹配专属模板时，优先使用维度模板；否则回退到策略类型模板。
模板配置默认读取：`./config/target-templates.json`。

如果你想切换模板文件，可用环境变量覆盖：

```bash
HIVEFLOW_TARGET_TEMPLATE_FILE=./config/my-target-templates.json uv run hiveflow targets generate --strategy "趋势动量策略"
```

JSON 输出示例：

```bash
uv run hiveflow targets generate --strategy "进攻突破策略" --output json
```

### 3.26 预览调仓建议

```bash
uv run hiveflow rebalance preview
```

说明：如果不传 `--strategy`，会自动使用当前策略（若未设置则退化为全目标持仓预览）。
当使用某个具体策略预览时，会同时输出该策略的类型与维度。
JSON 中会带 `risk_waterline` 与 `explanation` 字段；当标的风险为 `high` 且原建议为 `buy` 时，会被风险门控为 `hold`。

只预览某个策略：

```bash
uv run hiveflow rebalance preview --strategy "进攻型默认策略"
```

写入数据库（用于 summary 联动）：

```bash
uv run hiveflow rebalance preview --strategy "进攻型默认策略" --save
```

JSON 输出示例：

```bash
uv run hiveflow rebalance preview --strategy "进攻型默认策略" --output json
```

主题切换示例：

```bash
uv run hiveflow rebalance preview --theme minimal
```

## 4. 数据库路径

默认数据库路径：

`/Users/rongts/strat-flow/data/hiveflow.db`

可以通过环境变量覆盖：

```bash
HIVEFLOW_DATABASE_URL="sqlite:////Users/rongts/strat-flow/data/dev.db" uv run hiveflow bootstrap
```

## 5. 推荐日常流程

1. `uv run hiveflow bootstrap`（第一次或切换新库时执行）
2. `uv run hiveflow positions add ...`（录入持仓）
3. `uv run hiveflow positions list`（核对持仓）
4. `uv run hiveflow summary`（查看状态摘要）
5. `uv run hiveflow log ...`（记录关键决策）

## 6. 常见问题

如果提示找不到 `hiveflow` 命令，先执行：

```bash
uv sync
```

再重试：

```bash
uv run hiveflow --help
```
