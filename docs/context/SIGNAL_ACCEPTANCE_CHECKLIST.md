# SIGNAL_ACCEPTANCE_CHECKLIST

## 目的

用于信号系统 Phase 1 的一次性验收与后续回归核对。  
原则：只验收“系统输出数据能力”，不验收“投资推荐能力”。

## 验收范围

- `signal` 命令族（snapshot/category/history/show）
- `style` 命令族（backtest-rank/history/show）
- `context daily` 聚合输出
- 严格模式错误协议与系统日志落库
- JSON 契约一致性（实时输出、历史回放、envelope/schema）

## 验收清单（当前状态）

| 编号 | 验收项 | 通过标准 | 状态 |
|---|---|---|---|
| S1 | `signal snapshot` 真实计算 | 输出 24 信号，含 `category_metrics/conflict_matrix` | ✅ |
| S2 | 分类信号命令可用 | `trend/risk/confirm/regime/quality` 可独立输出 | ✅ |
| S3 | `style backtest-rank` 可用 | 输出 4 风格 `rank_table`，无推荐字段 | ✅ |
| S4 | 历史落库 | `signal/style` 执行成功后自动写库 | ✅ |
| S5 | 历史回放 | `signal show/style show` 与实时字段契约一致 | ✅ |
| S6 | 可复现元数据 | 输出 `feature_set_version/symbols_hash/params_hash/code_version` | ✅ |
| S7 | 风格报告字段 | 输出 `objective/constraints/search_method/best_candidate` | ✅ |
| S8 | 严格模式失败协议 | 返回统一错误对象并含 `trace_id` | ✅ |
| S9 | 系统日志 | 严格失败写入 `systemlog` | ✅ |
| S10 | `context daily` 聚合 | 输出 `check/drift/signal_latest/style_latest` | ✅ |
| S11 | `context daily` 契约 | 支持 `--output json --envelope` 与 `--json-schema` | ✅ |
| S12 | 来源时效控制 | 支持 `--strict-source latest|fresh --max-age-hours` | ✅ |
| S13 | 来源元信息 | 输出 `source_meta`（record_id/as_of/age_hours） | ✅ |
| S14 | 文档一致性 | 新手文档场景二与当前行为一致 | ✅ |
| S15 | 窗口审计契约 | `window_audit` 字段与版本定义形成独立契约文档 | ✅ |

## 关键命令回归（手工抽检）

```bash
uv run hiveflow signal snapshot --output json
uv run hiveflow signal history --output json
uv run hiveflow signal show <id> --output json

uv run hiveflow style backtest-rank --output json
uv run hiveflow style history --output json
uv run hiveflow style show <id> --output json

uv run hiveflow context daily --output json
uv run hiveflow context daily --output json --envelope
uv run hiveflow context daily --json-schema
uv run hiveflow context daily --output json --strict-source fresh --max-age-hours 24
```

## 测试基线（当前）

- `uv run pytest tests/test_signal_cli.py -q` → `25 passed`
- 回归集合：`uv run pytest tests/test_cli_check.py tests/test_risk_analysis_cli.py tests/test_cli.py tests/test_dynamic_backtest.py tests/test_quant_cli.py tests/test_positions_list_grid.py tests/test_perf_cli.py tests/test_blend_cli.py -q` → `122 passed`

## 结论

信号系统 Phase 1 验收通过，可进入维护模式。后续新增能力需先立项并更新里程碑文档。
