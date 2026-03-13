# 测试使用文档

本目录存放 HiveFlow 的单元测试，当前覆盖：

- CLI 命令可用性
- 启动默认配置与默认策略席位
- 目标持仓生成逻辑
- 实际持仓与目标持仓偏差计算及调仓建议

## 环境准备

在项目根目录执行：

```bash
uv sync --extra dev
```

## 如何运行测试

运行全部测试：

```bash
uv run python -m pytest -q
```

按文件运行：

```bash
uv run python -m pytest tests/test_cli.py -q
```

按关键字筛选：

```bash
uv run python -m pytest -k rebalance -q
```

## 测试文件说明

- `test_cli.py`：验证 CLI 主命令与子命令是否可用（`--help`、`log`、`summary`）。
- `test_bootstrap.py`：验证默认配置、默认席位和默认策略分类是否符合预期。
- `test_allocation_engine.py`：验证策略目标持仓生成是否正确。
- `test_rebalance_engine.py`：验证偏差计算、调仓建议和风险优先级映射逻辑。

## 常见问题

如果 `uv run pytest` 与预期环境不一致，优先使用：

```bash
uv run python -m pytest -q
```

这样可以确保使用当前虚拟环境中的 pytest 与依赖。
