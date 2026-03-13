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

主题切换（仅 pretty 输出生效）：

```bash
uv run hiveflow summary --theme hacker
uv run hiveflow summary --theme minimal
```

## 3. 核心命令

### 3.1 初始化本地数据库与基础数据

```bash
uv run hiveflow bootstrap
```

作用：

- 创建数据表
- 写入默认策略席位（进攻/防守/长期）
- 写入默认策略分类对应的基础策略

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
- `category`
- `thesis`
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

### 3.16 查看策略席位列表

```bash
uv run hiveflow slots list
```

JSON 输出示例：

```bash
uv run hiveflow slots list --output json
```

### 3.17 更新席位权重

```bash
uv run hiveflow slots set-weight --name "进攻席位" --weight 0.55
```

说明：更新成功后会自动写入一条 `decision_logs` 记录（类型：`slots-set-weight`）。

JSON 输出示例：

```bash
uv run hiveflow slots set-weight --name "进攻席位" --weight 0.55 --output json
```

### 3.18 查看目标持仓列表

```bash
uv run hiveflow targets list
```

JSON 输出示例：

```bash
uv run hiveflow targets list --output json
```

主题切换示例：

```bash
uv run hiveflow targets list --theme minimal
```

### 3.19 从 CSV 导入目标持仓

```bash
uv run hiveflow targets import --file ./target-allocations.csv
```

说明：导入成功后会自动写入一条 `decision_logs` 记录（类型：`targets-import`）。

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

### 3.20 下载（生成）目标持仓 CSV 模板

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

### 3.21 基于策略自动生成目标持仓

```bash
uv run hiveflow targets generate --strategy "进攻突破策略"
```

说明：会按策略分类自动套用默认权重模板，并覆盖该策略已有目标持仓。  
导入成功后会自动写入一条 `decision_logs` 记录（类型：`targets-generate`）。

JSON 输出示例：

```bash
uv run hiveflow targets generate --strategy "进攻突破策略" --output json
```

### 3.22 预览调仓建议

```bash
uv run hiveflow rebalance preview
```

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
