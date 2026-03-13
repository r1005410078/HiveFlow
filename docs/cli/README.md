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

### 3.3 查看系统摘要（当前为最小可行版本演示输出）

```bash
uv run hiveflow summary
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
2. `uv run hiveflow summary`（查看当前状态）
3. `uv run hiveflow log ...`（记录关键决策）

## 6. 常见问题

如果提示找不到 `hiveflow` 命令，先执行：

```bash
uv sync
```

再重试：

```bash
uv run hiveflow --help
```
