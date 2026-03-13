# HiveFlow 基础开发实施计划

> **给代理执行者：** 必须使用 `superpowers:subagent-driven-development`（如果当前环境支持子代理）或 `superpowers:executing-plans` 来执行本计划。步骤使用复选框语法（`- [x]`）进行跟踪。

## 执行状态（2026-03-13 回填）

- 已按 `superpowers:executing-plans` 的节奏完成基础实现与测试闭环。
- 本文复选框已按当前代码状态统一回填为完成。
- 代码层面：Chunk 1 ~ Chunk 5 的功能性目标已落地（项目骨架、领域模型、bootstrap、allocation/rebalance/risk、CLI）。
- 增量层面：已完成 Chunk 6（真实持仓闭环最小版：`positions add/list` + `summary` 读取真实数据库）。
- 增量层面：已完成 Chunk 7（`positions import`：CSV 导入持仓，支持 `append/replace` 与 JSON 输出）。
- 验证层面：当前测试集通过（`uv run python -m pytest -q` -> `19 passed`）。
- 文档层面：已补充 CLI 使用文档与测试使用文档。
- 与原计划差异：计划要求“每任务单独提交”，实际执行为集中开发后一次性提交。
 - 回填说明：后续增量按“实现后即时回填”方式维护本计划。

**目标：** 搭建 HiveFlow 第一版可运行基础：一个本地 Python 应用，能够存储核心领域数据、加载策略和持仓、生成目标配比、比较实际与目标持仓，并输出调仓建议。

**架构：** 先从单一 Python 代码库和本地 SQLite 数据库开始。代码按领域对象组织，而不是按界面层组织：策略、席位、持仓、风险信号、配比、建议和日志。优先打通最小可运行 CLI 流程，再逐步扩展。

**技术栈：** Python 3.12+、uv、Typer、Pydantic v2、SQLModel、SQLite、pytest

---

## 文件结构

第一阶段实现建议采用下面这套结构：

- `pyproject.toml`
  项目元数据、依赖、pytest 配置
- `.python-version`
  本地 Python 版本固定
- `src/hiveflow/__init__.py`
  包标记文件
- `src/hiveflow/cli.py`
  Typer 命令入口
- `src/hiveflow/config.py`
  应用配置和数据库路径
- `src/hiveflow/db.py`
  数据库引擎和 session 辅助
- `src/hiveflow/domain/strategies.py`
  策略与策略分类领域模型
- `src/hiveflow/domain/slots.py`
  策略席位领域模型
- `src/hiveflow/domain/positions.py`
  实际持仓领域模型
- `src/hiveflow/domain/risk.py`
  风险水位领域模型
- `src/hiveflow/domain/allocations.py`
  目标配比与资产配比领域模型
- `src/hiveflow/domain/suggestions.py`
  调仓建议领域模型
- `src/hiveflow/domain/decision_logs.py`
  决策日志和用户偏好领域模型
- `src/hiveflow/services/bootstrap.py`
  初始化默认席位和策略分类
- `src/hiveflow/services/allocation_engine.py`
  根据当前策略生成目标配比
- `src/hiveflow/services/rebalance_engine.py`
  比较实际与目标持仓并生成建议
- `src/hiveflow/services/risk_engine.py`
  保存并解释每个持仓的风险状态
- `tests/test_bootstrap.py`
  初始化与种子数据测试
- `tests/test_allocation_engine.py`
  目标配比生成测试
- `tests/test_rebalance_engine.py`
  调仓建议测试
- `tests/test_cli.py`
  CLI 端到端基本流程测试
- `docs/architecture/data-model.md`
  面向开发者的轻量数据模型说明

## Chunk 1：项目骨架

### 任务 1：初始化 Python 项目元数据

**文件：**
- 新建：`pyproject.toml`
- 新建：`.python-version`

- [x] **步骤 1：先写失败测试**

创建 `tests/test_cli.py`，先写一个仅导入 CLI 模块的占位测试：

```python
from hiveflow.cli import app


def test_cli_module_imports() -> None:
    assert app is not None
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_cli.py -v`  
预期：因为包和依赖尚未建立，出现导入错误并 FAIL

- [x] **步骤 3：写最小项目元数据**

创建 `pyproject.toml`，至少包含：

- 项目名 `hiveflow`
- 依赖：`typer`、`pydantic`、`sqlmodel`
- 开发依赖：`pytest`
- `src/` 目录的包配置

创建 `.python-version`：

```text
3.12
```

- [x] **步骤 4：再次运行测试，确认它因预期原因继续失败**

运行：`uv run pytest tests/test_cli.py -v`  
预期：因为 `src/hiveflow/cli.py` 还不存在而 FAIL，但依赖解析已经正常工作

- [x] **步骤 5：提交**

```bash
git add pyproject.toml .python-version tests/test_cli.py
git commit -m "chore: initialize hiveflow project metadata"
```

### 任务 2：补上包骨架和 CLI 入口

**文件：**
- 新建：`src/hiveflow/__init__.py`
- 新建：`src/hiveflow/cli.py`

- [x] **步骤 1：先写失败测试**

扩展 `tests/test_cli.py`：

```python
from typer.testing import CliRunner

from hiveflow.cli import app


def test_cli_shows_help() -> None:
    result = CliRunner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "HiveFlow" in result.stdout
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_cli.py::test_cli_shows_help -v`  
预期：因为 CLI 入口还不存在而 FAIL

- [x] **步骤 3：写最小实现**

创建 `src/hiveflow/__init__.py`：

```python
__all__ = ["__version__"]

__version__ = "0.1.0"
```

创建 `src/hiveflow/cli.py`：

```python
import typer

app = typer.Typer(help="HiveFlow local asset decision system.")


@app.callback()
def main() -> None:
    """HiveFlow CLI."""
```

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_cli.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/__init__.py src/hiveflow/cli.py tests/test_cli.py
git commit -m "feat: add minimal hiveflow cli"
```

## Chunk 2：核心数据模型

### 任务 3：增加数据库配置

**文件：**
- 新建：`src/hiveflow/config.py`
- 新建：`src/hiveflow/db.py`
- 测试：`tests/test_bootstrap.py`

- [x] **步骤 1：先写失败测试**

创建 `tests/test_bootstrap.py`：

```python
from hiveflow.config import Settings


def test_default_database_url_uses_sqlite() -> None:
    settings = Settings()
    assert settings.database_url.startswith("sqlite")
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_bootstrap.py::test_default_database_url_uses_sqlite -v`  
预期：因为配置模块不存在而 FAIL

- [x] **步骤 3：写最小实现**

创建 `src/hiveflow/config.py`，提供 Pydantic settings 模型和默认 SQLite 路径。

创建 `src/hiveflow/db.py`，至少提供：

- SQLModel engine 工厂
- session 辅助函数
- metadata create 辅助函数

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_bootstrap.py::test_default_database_url_uses_sqlite -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/config.py src/hiveflow/db.py tests/test_bootstrap.py
git commit -m "feat: add database configuration"
```

### 任务 4：增加核心领域模型

**文件：**
- 新建：`src/hiveflow/domain/strategies.py`
- 新建：`src/hiveflow/domain/slots.py`
- 新建：`src/hiveflow/domain/positions.py`
- 新建：`src/hiveflow/domain/risk.py`
- 新建：`src/hiveflow/domain/allocations.py`
- 新建：`src/hiveflow/domain/suggestions.py`
- 新建：`src/hiveflow/domain/decision_logs.py`
- 新建：`docs/architecture/data-model.md`
- 测试：`tests/test_bootstrap.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_bootstrap.py` 中增加：

```python
from hiveflow.domain.slots import StrategySlot


def test_strategy_slot_has_name_and_purpose() -> None:
    slot = StrategySlot(name="进攻席位", purpose="进攻资金")
    assert slot.name == "进攻席位"
    assert slot.purpose == "进攻资金"
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_bootstrap.py::test_strategy_slot_has_name_and_purpose -v`  
预期：因为领域模型不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加基于 SQLModel / Pydantic 的模型：

- Strategy
- StrategySlot
- Position
- RiskSignal
- TargetAllocation
- RebalanceSuggestion
- DecisionLog
- UserPreference

编写 `docs/architecture/data-model.md`，说明各模型职责和关系。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_bootstrap.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/domain docs/architecture/data-model.md tests/test_bootstrap.py
git commit -m "feat: add core hiveflow domain models"
```

## Chunk 3：初始化 MVP 地基

### 任务 5：种入三个默认策略席位

**文件：**
- 新建：`src/hiveflow/services/bootstrap.py`
- 修改：`src/hiveflow/cli.py`
- 测试：`tests/test_bootstrap.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_bootstrap.py` 中增加：

```python
from hiveflow.services.bootstrap import default_slots


def test_default_slots_include_attack_defense_long_term() -> None:
    names = [slot.name for slot in default_slots()]
    assert names == ["进攻席位", "防守席位", "长期席位"]
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_bootstrap.py::test_default_slots_include_attack_defense_long_term -v`  
预期：因为 bootstrap 服务不存在而 FAIL

- [x] **步骤 3：写最小实现**

创建 bootstrap 辅助逻辑，定义：

- 三个默认席位
- 每个席位的默认用途
- 每个席位允许使用的默认策略分类

并增加一个 CLI 命令：

- `hiveflow bootstrap`

该命令负责建表并写入基础种子数据。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_bootstrap.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/bootstrap.py src/hiveflow/cli.py tests/test_bootstrap.py
git commit -m "feat: seed default strategy slots"
```

### 任务 6：种入第一版策略分类

**文件：**
- 修改：`src/hiveflow/services/bootstrap.py`
- 测试：`tests/test_bootstrap.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_bootstrap.py` 中增加：

```python
from hiveflow.services.bootstrap import default_strategy_categories


def test_default_strategy_categories_match_slots() -> None:
    categories = default_strategy_categories()
    assert set(categories) == {"进攻型", "防守型", "长期型"}
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_bootstrap.py::test_default_strategy_categories_match_slots -v`  
预期：因为辅助函数不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加三类基础策略分类，并写入与默认席位相匹配的种子数据。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_bootstrap.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/bootstrap.py tests/test_bootstrap.py
git commit -m "feat: add baseline strategy taxonomy"
```

## Chunk 4：目标配比与调仓流程

### 任务 7：实现目标持仓生成

**文件：**
- 新建：`src/hiveflow/services/allocation_engine.py`
- 测试：`tests/test_allocation_engine.py`

- [x] **步骤 1：先写失败测试**

创建 `tests/test_allocation_engine.py`：

```python
from hiveflow.services.allocation_engine import generate_target_allocations


def test_generate_target_allocations_returns_targets_for_selected_strategy() -> None:
    targets = generate_target_allocations(
        strategy_name="测试趋势策略",
        allocations={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert len(targets) == 3
    assert targets[0].strategy_name == "测试趋势策略"
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_allocation_engine.py -v`  
预期：因为服务不存在而 FAIL

- [x] **步骤 3：写最小实现**

创建一个最小配比引擎，支持：

- 接收当前选中的策略名称
- 接收归一化后的目标权重
- 返回结构化的目标配比记录

第一版这里先明确走最稳的路径：

- 先支持“输入目标权重 -> 生成目标持仓”
- 先把目标持仓的数据结构、存储和流程打通
- 暂不在这一任务里实现复杂策略自动计算逻辑

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_allocation_engine.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/allocation_engine.py tests/test_allocation_engine.py
git commit -m "feat: add target allocation engine"
```

### 任务 8：实现实际持仓与目标持仓比较

**文件：**
- 新建：`src/hiveflow/services/rebalance_engine.py`
- 测试：`tests/test_rebalance_engine.py`

- [x] **步骤 1：先写失败测试**

创建 `tests/test_rebalance_engine.py`：

```python
from hiveflow.services.rebalance_engine import compare_actual_to_target


def test_compare_actual_to_target_calculates_deltas() -> None:
    result = compare_actual_to_target(
        actual={"BTC": 0.6, "ETH": 0.2, "USDT": 0.2},
        target={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert result["BTC"] == 0.1
    assert result["ETH"] == -0.1
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_rebalance_engine.py::test_compare_actual_to_target_calculates_deltas -v`  
预期：因为服务不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加比较逻辑，输出每个资产在实际权重和目标权重之间的偏差值。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_rebalance_engine.py::test_compare_actual_to_target_calculates_deltas -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/rebalance_engine.py tests/test_rebalance_engine.py
git commit -m "feat: compare actual and target allocations"
```

### 任务 9：实现调仓建议生成

**文件：**
- 修改：`src/hiveflow/services/rebalance_engine.py`
- 测试：`tests/test_rebalance_engine.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_rebalance_engine.py` 中增加：

```python
from hiveflow.services.rebalance_engine import generate_rebalance_suggestions


def test_generate_rebalance_suggestions_includes_action_and_priority() -> None:
    suggestions = generate_rebalance_suggestions(
        actual={"BTC": 0.6, "ETH": 0.2, "USDT": 0.2},
        target={"BTC": 0.5, "ETH": 0.3, "USDT": 0.2},
    )
    assert suggestions[0].action in {"buy", "sell", "hold"}
    assert suggestions[0].priority in {"high", "medium", "low"}
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_rebalance_engine.py -v`  
预期：因为建议生成逻辑不存在而 FAIL

- [x] **步骤 3：写最小实现**

扩展 rebalance engine，让它输出结构化建议，至少包含：

- 资产代码
- 偏差值
- 推荐动作
- 优先级
- 原因说明

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_rebalance_engine.py -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/rebalance_engine.py tests/test_rebalance_engine.py
git commit -m "feat: add rebalance suggestion generation"
```

## Chunk 5：风险、日志和最小可运行 CLI

### 任务 10：实现基础风险信号处理

**文件：**
- 新建：`src/hiveflow/services/risk_engine.py`
- 测试：`tests/test_rebalance_engine.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_rebalance_engine.py` 中增加：

```python
from hiveflow.services.risk_engine import classify_priority_from_risk


def test_high_risk_maps_to_high_priority() -> None:
    assert classify_priority_from_risk("high") == "high"
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_rebalance_engine.py::test_high_risk_maps_to_high_priority -v`  
预期：因为 risk engine 不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加一个简单风险辅助逻辑，把已存储的风险状态映射为建议优先级默认值。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_rebalance_engine.py::test_high_risk_maps_to_high_priority -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/services/risk_engine.py tests/test_rebalance_engine.py
git commit -m "feat: add risk priority mapping"
```

### 任务 11：增加决策日志记录

**文件：**
- 修改：`src/hiveflow/domain/decision_logs.py`
- 修改：`src/hiveflow/cli.py`
- 测试：`tests/test_cli.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_cli.py` 中增加：

```python
def test_log_command_is_available() -> None:
    result = CliRunner().invoke(app, ["log", "--help"])
    assert result.exit_code == 0
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_cli.py::test_log_command_is_available -v`  
预期：因为命令不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加 `log` 命令组，支持写入简单决策日志，至少包括：

- summary
- decision type
- optional notes

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_cli.py::test_log_command_is_available -v`  
预期：PASS

- [x] **步骤 5：提交**

```bash
git add src/hiveflow/domain/decision_logs.py src/hiveflow/cli.py tests/test_cli.py
git commit -m "feat: add decision log command"
```

### 任务 12：增加端到端 summary 命令

**文件：**
- 修改：`src/hiveflow/cli.py`
- 测试：`tests/test_cli.py`

- [x] **步骤 1：先写失败测试**

在 `tests/test_cli.py` 中增加：

```python
def test_summary_command_is_available() -> None:
    result = CliRunner().invoke(app, ["summary", "--help"])
    assert result.exit_code == 0
```

- [x] **步骤 2：运行测试，确认它失败**

运行：`uv run pytest tests/test_cli.py::test_summary_command_is_available -v`  
预期：因为命令不存在而 FAIL

- [x] **步骤 3：写最小实现**

增加 `summary` 命令，用于输出：

- 当前持仓
- 目标配比
- 风险状态
- 调仓建议摘要

第一版允许使用种子数据或 demo 数据来打通端到端流程。

- [x] **步骤 4：运行测试，确认通过**

运行：`uv run pytest tests/test_cli.py -v`  
预期：PASS

- [x] **步骤 5：运行完整测试集**

运行：`uv run pytest -v`  
预期：PASS

- [x] **步骤 6：提交**

```bash
git add src/hiveflow/cli.py tests/test_cli.py
git commit -m "feat: add hiveflow summary command"
```

## 计划说明

- 第一版保持本地运行、同步执行。
- 这个阶段不要引入 Web 服务、消息队列或远程 API。
- 策略逻辑和席位逻辑必须和界面代码分开。
- 第一轮端到端实现允许使用种子数据或 demo 数据，但领域边界必须保持清晰。

## 执行交接

计划已完成，并保存到 `docs/superpowers/plans/2026-03-13-hiveflow-foundation.md`。可以开始执行。
