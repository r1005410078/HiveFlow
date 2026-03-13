# Market Data Contract

## 目的

定义 HiveFlow 回测与风险计算使用的统一行情输入格式，避免不同命令读同一份数据却产生不同解释。

## CSV 必填列

1. `symbol`
2. `timestamp`
3. `open`
4. `high`
5. `low`
6. `close`
7. `volume`

## 字段规则

- `symbol`：非空，建议大写（如 `BTC`、`ETH`）。
- `timestamp`：必须为 UTC 时间，格式为 ISO8601，推荐 `Z` 结尾，例如 `2026-03-13T00:00:00Z`。
- `open/high/low/close/volume`：必须为数值且不能为负。
- `high >= low`。

## 示例

```csv
symbol,timestamp,open,high,low,close,volume
BTC,2026-03-13T00:00:00Z,100000,102000,99000,101500,1200
ETH,2026-03-13T00:00:00Z,3000,3100,2950,3080,8500
```

## CLI 支持

- 生成模板：`uv run hiveflow market-data template`
- 校验文件：`uv run hiveflow market-data validate --file ./prices.csv`
