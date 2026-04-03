# HiveFlow 文档导航

> 文档目标：提供统一阅读路径与术语入口。适用对象：所有参与 HiveFlow 设计、开发、评审的成员。

补充说明：
- 若关注“当前可运行能力”，优先阅读 `GETTING_STARTED.md`、`BEGINNER_QUICKSTART.md`、`ARCHITECTURE.md`，并以 `cargo run -- --help`（或 `hf --help`）为最终命令面依据。
- `docs/requirements/` 与 `docs/superpowers/` 下文档包含需求、方案与实施计划，部分内容可能是目标态，不代表已全部落地。

## 按角色阅读路径（推荐）

| 角色 | 第一步 | 第二步 | 第三步 |
|---|---|---|---|
| 策略研发 | [ARCHITECTURE.md](ARCHITECTURE.md)（分层职责、上线闸门） | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（AI 边界、审批边界） | [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)（选型结论与复评机制） |
| AI/Agent 开发 | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（Skill 路由、审计要求） | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（输出合同） | [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)（样例与校验命令） |
| 量化评估使用方 | [FACTOR_OPTIMIZATION_P1_USAGE.md](FACTOR_OPTIMIZATION_P1_USAGE.md)（P1 使用与字段说明） | [FACTOR_OPTIMIZATION_P2_USAGE.md](FACTOR_OPTIMIZATION_P2_USAGE.md)（Top5 组合推荐 + release_gate 字段） | [analysis/factor_optimization/replay/README.md](analysis/factor_optimization/replay/README.md)（P3 回放与门禁报告） |
| 平台工程 | [ARCHITECTURE.md](ARCHITECTURE.md)（G1/G2/G3、全链路契约） | [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)（技术边界、退出条件） | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（审计字段、接入解析） |
| 测试与 CI | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（机器校验规则） | [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)（正反样例、脚本） | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（语义边界，尤其 `web_search`） |

## 通用阅读顺序

1. [ARCHITECTURE.md](ARCHITECTURE.md)
2. [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)
3. [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)
4. [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)
5. [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)
6. [FACTOR_OPTIMIZATION_P1_USAGE.md](FACTOR_OPTIMIZATION_P1_USAGE.md)
7. [FACTOR_OPTIMIZATION_P2_USAGE.md](FACTOR_OPTIMIZATION_P2_USAGE.md)
8. [analysis/factor_optimization/replay/README.md](analysis/factor_optimization/replay/README.md)

## 该看哪份文档

- 看系统全局设计：`ARCHITECTURE.md`
- 看 AI 如何介入：`AI_SKILLS_INTEGRATION.md`
- 看技术选型结论：`TECH_STACK_DECISION.md`
- 看 CLI 输出该长什么样：`CLI_OUTPUT_SCHEMA.json`
- 看可复制样例与校验命令：`CLI_OUTPUT_EXAMPLES.md`
- 看 P1 因子优化如何使用：`FACTOR_OPTIMIZATION_P1_USAGE.md`
- 看 P2 Top5 组合推荐与门禁字段：`FACTOR_OPTIMIZATION_P2_USAGE.md`
- 看 P3 回放执行与报告解读：`analysis/factor_optimization/replay/README.md`

## 一句话关系图

`ARCHITECTURE.md` 定义系统分层与治理边界 -> `AI_SKILLS_INTEGRATION.md` 定义 AI 协作与审批边界 -> `TECH_STACK_DECISION.md` 固化技术选型与复评机制 -> `CLI_OUTPUT_SCHEMA.json` 定义机器可校验输出合同 -> `CLI_OUTPUT_EXAMPLES.md` 提供样例与校验入口 -> `FACTOR_OPTIMIZATION_P1_USAGE.md` 提供 P1 因子优化实操指南 -> `FACTOR_OPTIMIZATION_P2_USAGE.md` 提供 P2 Top5 与 release_gate 字段指南 -> `analysis/factor_optimization/replay/README.md` 提供 P3 回放与门禁审计指南。
