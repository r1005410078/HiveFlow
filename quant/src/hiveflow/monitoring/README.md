# L8 Monitoring Subdomain

## Purpose
L8 负责运行监控、告警与复盘记录，形成闭环证据。

## Responsibilities
- 记录 run_id 级别运行快照
- 生成偏离/异常告警事件
- 为后续复盘提供审计数据

## Input / Output
- Input: pipeline 运行结果、执行状态、风险事件
- Output: 监控记录与告警文件（JSON/NDJSON）

## DDD Layers
- `domain/`: 监控事件与告警对象
- `application/`: 监控与告警用例
- `infrastructure/`: 文件持久化与通知适配
- `interfaces/`: 监控输出 DTO
