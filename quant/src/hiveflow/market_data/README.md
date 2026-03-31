# L1 Market Data Subdomain

## Purpose
L1 负责行情采集、清洗与落盘，是全链路数据可信性的入口层。

## Responsibilities
- 拉取日频行情与复权字段
- 执行基础清洗与字段标准化
- 落盘 Parquet（按 `as_of` 分区）
- 生成并关联 `data_manifest` 所需元数据

## Input / Output
- Input: 外部数据源原始行情（腾讯数跟主源，akshare 兜底）
- Output: 标准行情表（close/volume/adj_factor/effective_date...）+ 分区文件路径

## DDD Layers
- `domain/`: 行情实体、字段口径与 PIT 规则
- `application/`: 采集/清洗/落盘用例
- `infrastructure/`: 数据源客户端与 Parquet 仓储
- `interfaces/`: 子域对外请求/响应模型
