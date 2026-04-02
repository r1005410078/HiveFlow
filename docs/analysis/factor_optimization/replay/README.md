# Factor Optimize Replay Reports

本目录用于存放 `hf factor optimize` 的离线回放产物。

脚本会按日期区间逐日调用 `POST /api/v1/factor-optimization/evaluate`，汇总每一天的：

- `data.release_gate.status`
- `data.correlation_analysis.alert_count`
- `data.top_combinations.items[0].factors`

注意：

- `fetch_status=error` 表示网络或解析失败。
- 这类错误不计入业务 `pass/watch/fail`。
- `error_days` 单独统计抓取失败的天数。

## 运行方式

在仓库根目录执行：

```bash
python scripts/factor_optimize_replay.py \
  --server-url http://127.0.0.1:8000 \
  --start-date 2026-03-01 \
  --end-date 2026-03-31 \
  --factors momentum_20,inv_volatility_20,turnover_rate,max_drawdown_60,trend_stability_20,relative_strength_vs_index
```

参数说明：

- `--server-url`：服务端地址，默认 `http://127.0.0.1:8000`
- `--start-date`：起始日期，必填，格式 `YYYY-MM-DD`
- `--end-date`：结束日期，必填，格式 `YYYY-MM-DD`
- `--factors`：逗号分隔的因子列表，必填
- `--output-dir`：输出目录，默认 `docs/analysis/factor_optimization/replay`

## 输出文件

脚本会生成同名的一对文件：

- `replay_<start>_<end>.json`
- `replay_<start>_<end>.md`

### JSON 格式

JSON 报告包含：

- `summary.days`
- `summary.error_days`
- `summary.pass_days`
- `summary.watch_days`
- `summary.fail_days`
- `summary.avg_alert_count`
- `summary.top1_change_days`
- `daily_items[]`

`daily_items[]` 中，抓取失败的条目会带有：

- `fetch_status=error`
- `release_gate_status=unknown`
- `error_message`

### Markdown 格式

Markdown 报告包含：

- `error_days` 摘要
- `error_dates` 列表
- Summary 区块
- `fail/watch` 日期列表
- Top1 组合变化天数
- Daily Items 明细
