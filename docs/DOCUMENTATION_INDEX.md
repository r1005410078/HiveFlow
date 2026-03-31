# HiveFlow 文档导航

> 文档目标：提供统一阅读路径与术语入口。适用对象：所有参与 HiveFlow 设计、开发、评审的成员。

## 按角色阅读路径（推荐）

| 角色 | 第一步 | 第二步 | 第三步 |
|---|---|---|---|
| 策略研发 | [ARCHITECTURE.md](ARCHITECTURE.md)（分层职责、上线闸门） | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（AI 边界、审批边界） | [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)（选型结论与复评机制） |
| AI/Agent 开发 | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（Skill 路由、审计要求） | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（输出合同） | [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)（样例与校验命令） |
| 平台工程 | [ARCHITECTURE.md](ARCHITECTURE.md)（G1/G2/G3、全链路契约） | [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)（技术边界、退出条件） | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（审计字段、接入解析） |
| 测试与 CI | [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)（机器校验规则） | [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)（正反样例、脚本） | [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)（语义边界，尤其 `web_search`） |

## 通用阅读顺序

1. [ARCHITECTURE.md](ARCHITECTURE.md)
2. [AI_SKILLS_INTEGRATION.md](AI_SKILLS_INTEGRATION.md)
3. [TECH_STACK_DECISION.md](TECH_STACK_DECISION.md)
4. [CLI_OUTPUT_SCHEMA.json](CLI_OUTPUT_SCHEMA.json)
5. [CLI_OUTPUT_EXAMPLES.md](CLI_OUTPUT_EXAMPLES.md)

## 该看哪份文档

- 看系统全局设计：`ARCHITECTURE.md`
- 看 AI 如何介入：`AI_SKILLS_INTEGRATION.md`
- 看技术选型结论：`TECH_STACK_DECISION.md`
- 看 CLI 输出该长什么样：`CLI_OUTPUT_SCHEMA.json`
- 看可复制样例与校验命令：`CLI_OUTPUT_EXAMPLES.md`

## 一句话关系图

`ARCHITECTURE.md` 定义系统分层与治理边界 -> `AI_SKILLS_INTEGRATION.md` 定义 AI 协作与审批边界 -> `TECH_STACK_DECISION.md` 固化技术选型与复评机制 -> `CLI_OUTPUT_SCHEMA.json` 定义机器可校验输出合同 -> `CLI_OUTPUT_EXAMPLES.md` 提供样例与校验入口。
