# WINDOW_AUDIT_CONTRACT

## 目的

定义 `hiveflow context daily` 输出中的 `window_audit` 契约，供 Agent、前端和下游服务稳定消费。

## 适用范围

- `context daily` 成功输出：`summary.window_audit`
- `context daily` 严格失败输出（`--strict-window all`）：`details.window_audit`

## 版本

- 当前版本：`window_audit_schema_version = "v1"`
- 兼容策略：新增字段只增不删；旧平铺字段继续保留，避免破坏既有消费方。

## 字段定义（v1）

| 字段 | 类型 | 含义 |
|---|---|---|
| `window_audit_schema_version` | `string` | 契约版本，当前固定 `v1` |
| `windows_requested` | `number[]` | 请求窗口列表（按输入顺序） |
| `window_count_requested` | `number` | 请求窗口数量 |
| `window_count_success` | `number` | 成功窗口数量 |
| `window_count_failed` | `number` | 失败窗口数量 |
| `window_count_total_computed` | `number` | 执行窗口总数（成功+失败） |
| `is_window_audit_consistent` | `boolean` | 审计一致性结论（窗口数与状态映射覆盖是否一致） |
| `window_keys_success` | `string[]` | 成功窗口键（如 `w24`） |
| `window_keys_failed` | `string[]` | 失败窗口键（如 `w7`） |
| `window_status_map` | `object` | 窗口状态映射（`wxx -> ok/failed`），覆盖全部请求窗口 |
| `window_failures` | `object[]` | 失败详情列表（含 `window_key/component/reason/details`） |

## 示例（成功，全部窗口成功）

```json
{
  "window_audit_schema_version": "v1",
  "windows_requested": [12, 24],
  "window_count_requested": 2,
  "window_count_success": 2,
  "window_count_failed": 0,
  "window_count_total_computed": 2,
  "is_window_audit_consistent": true,
  "window_keys_success": ["w12", "w24"],
  "window_keys_failed": [],
  "window_status_map": {
    "w12": "ok",
    "w24": "ok"
  },
  "window_failures": []
}
```

## 示例（严格失败，部分窗口失败）

```json
{
  "window_audit_schema_version": "v1",
  "windows_requested": [24, 7, 30],
  "window_count_requested": 3,
  "window_count_success": 2,
  "window_count_failed": 1,
  "window_count_total_computed": 3,
  "is_window_audit_consistent": true,
  "window_keys_success": ["w24", "w30"],
  "window_keys_failed": ["w7"],
  "window_status_map": {
    "w24": "ok",
    "w7": "failed",
    "w30": "ok"
  },
  "window_failures": [
    {
      "window_key": "w7",
      "component": "style",
      "reason": "mocked window failure",
      "details": {
        "strict_mode": true,
        "failed_style": "w7"
      }
    }
  ]
}
```
