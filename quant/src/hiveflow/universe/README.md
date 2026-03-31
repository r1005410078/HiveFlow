# L0 Universe Subdomain

## Purpose
L0 负责定义可交易标的池（Universe），输出当前交易日可参与后续计算的证券集合。

## Responsibilities
- 过滤 ST、停牌、上市不足阈值（MVP: 60 日）
- 输出过滤原因码，便于审计与复现
- 与 `as_of` 对齐，保证后续层使用同一业务时点

## Input / Output
- Input: 候选标的基础属性（symbol、is_st、is_suspended、listed_days...）
- Output: `universe_snapshot(as_of, symbols, reason_codes, version)`

## DDD Layers
- `domain/`: 标的筛选规则和值对象（不依赖外部 IO）
- `application/`: 标的池构建用例编排
- `infrastructure/`: 数据加载/持久化适配（Parquet 或外部源）
- `interfaces/`: 对外 DTO 与序列化
