# AGENTS.md

本文件定义本项目的协作规则与新会话启动顺序。

## 1. 新会话必读顺序

每次打开新窗口，先读以下文件：

1. `docs/context/START_HERE.md`
2. `docs/context/PROJECT_CONTEXT.md`
3. `docs/context/CURRENT_STATE.md`
4. `docs/context/SESSION_LOG.md`（只看最新日期段）

## 2. 执行规则

- 先理解上下文，再改代码。
- 所有新增能力先补测试，再实现（TDD）。
- 修改完成后必须跑测试并给出结果。
- 所有 git 提交信息必须使用中文。
- 提交信息格式统一为：`类型: 简述（中文）`（示例：`feat: 增加当前策略设置命令`）。
- 不提交本地运行数据文件（如 `data/`、本地 CSV 样例）。

## 3. 文档维护规则

- 发生“产品决策变化”时，更新 `PROJECT_CONTEXT.md`。
- 发生“实现进度变化”时，更新 `CURRENT_STATE.md`。
- 每次会话结束，向 `SESSION_LOG.md` 追加简短记录（日期 + 决策 + 结果）。
