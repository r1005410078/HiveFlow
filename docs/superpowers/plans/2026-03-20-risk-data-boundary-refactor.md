# 风险数据边界改造 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将“持仓风险分析”统一改造为“持仓风险数据输出（系统）+ 风险分析建议（Agent）”，确保术语、命令文案、JSON契约与文档完全一致。  

**Architecture:** 保持现有计算能力不变，只做边界收口：CLI 文案与文档改名、JSON 增加 `decision_boundary` 元数据、兼容旧命令语义。通过测试先行保证无行为回归。  

**Tech Stack:** Python + Typer CLI + SQLModel + pytest + Markdown docs

---

## Chunk 1: 术语与契约基线冻结

### Task 1: 冻结边界字典（Data vs Decision）

**Files:**
- Create: `docs/context/BOUNDARY_GLOSSARY.md`
- Modify: `docs/context/PROJECT_CONTEXT.md`
- Test: `tests/test_cli.py`

- [ ] **Step 1: 写失败测试（文案/契约）**
  - 在 `tests/test_cli.py` 增加断言：`risk-analysis` JSON 含 `decision_boundary.system="data_only"`。
- [ ] **Step 2: 运行单测确认失败**
  - Run: `uv run pytest tests/test_cli.py -k decision_boundary -q`
- [ ] **Step 3: 最小实现**
  - 在 `risk-analysis assets/portfolio`、`check`、`context daily` JSON 输出新增：
    - `decision_boundary.system = "data_only"`
    - `decision_boundary.agent = "analysis_and_decision"`
- [ ] **Step 4: 运行单测确认通过**
  - Run: `uv run pytest tests/test_cli.py -k decision_boundary -q`
- [ ] **Step 5: 提交**
  - `git commit -m "feat: 增加风险数据输出边界元信息"`

## Chunk 2: CLI 文案改造（不破坏兼容）

### Task 2: 命令帮助与输出标题改名

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_cli_check.py`, `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**
  - 断言帮助文案从“风险分析”改为“风险数据输出”。
- [ ] **Step 2: 运行失败测试**
  - Run: `uv run pytest tests/test_cli_check.py tests/test_signal_cli.py -q`
- [ ] **Step 3: 最小实现**
  - 仅修改 help/title/提示文案，不改字段名与命令路径。
- [ ] **Step 4: 运行测试确认通过**
  - Run: `uv run pytest tests/test_cli_check.py tests/test_signal_cli.py -q`
- [ ] **Step 5: 提交**
  - `git commit -m "refactor: 统一风险数据输出文案"`

## Chunk 3: 文档与验收同步

### Task 3: 全文档边界收口

**Files:**
- Modify: `docs/cli/README.md`
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`
- Modify: `docs/context/SIGNAL_ACCEPTANCE_CHECKLIST.md`

- [ ] **Step 1: 更新文档措辞**
  - 将“系统分析风险”统一改为“系统输出风险数据”。
- [ ] **Step 2: 增加 Agent 使用示例**
  - 在 README 增加“系统输出 + Agent 判断”的调用示例。
- [ ] **Step 3: 文档一致性自检**
  - Run: `rg -n "风险分析|推荐|系统判断" docs`
- [ ] **Step 4: 提交**
  - `git commit -m "docs: 收口风险数据边界表述"`

## Chunk 4: 回归与发布门槛

### Task 4: 全量回归

**Files:**
- Modify: `docs/context/CURRENT_STATE.md`
- Modify: `docs/context/SESSION_LOG.md`

- [ ] **Step 1: 执行回归测试**
  - Run: `uv run pytest tests/test_signal_cli.py tests/test_cli.py tests/test_cli_check.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q`
- [ ] **Step 2: 记录测试结果**
  - 将通过结果写入 `CURRENT_STATE.md` 与 `SESSION_LOG.md`。
- [ ] **Step 3: 最终提交**
  - `git commit -m "chore: 完成风险数据边界改造回归收口"`

## 交付完成定义（DoD）

- 所有相关命令 JSON 明确标记 `decision_boundary`。
- CLI 与文档不再出现“系统做投资判断”的歧义表述。
- 兼容性不破坏（命令路径、核心字段不变）。
- 回归测试全绿并记录到上下文文档。
