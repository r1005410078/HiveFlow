# CLI `hf doctor` Implementation Plan

> **For agentic workers:** 按顺序勾选；每步可单独提交。

**Goal:** 实现 `hf doctor`，输出标准 CLI envelope，并通过 `make check`。

**Architecture:** `cmd` → `application/handlers/doctor` → `infrastructure`（`config_loader` + `http_client` 探测）；不新增 Python 路由。

**Tech Stack:** Rust / clap / reqwest / serde_json / chrono；JSON Schema + jq 校验脚本。

**Verification：** `make check` 已通过（含方案 B：`GET /v1/system/doctor` + `data.quant`）。

---

## Tasks（v1 本地探测）

- [x] 1. 更新 `docs/CLI_OUTPUT_SCHEMA.json`：为 `command == "hf doctor"` 增加 `data` 形状约束。
- [x] 2. 更新 `scripts/validate_cli_output.sh`：`hf doctor` 的 `data` 字段 jq 断言。
- [x] 3. 新增 fixture `quant/tests/fixtures/cli_output/valid/doctor_ok.json`。
- [x] 4. 更新 `docs/CLI_OUTPUT_EXAMPLES.md`：`hf doctor` 示例段落。
- [x] 5. `config_loader`：新增 `default_config_path()`；`load_default_config` 复用该路径。
- [x] 6. `http_client`：新增 `OpenapiProbeOutcome` + `probe_openapi_json`（与 `build_client` 一致处理 localhost 代理）。
- [x] 7. `cmd/doctor.rs` + `AppCommand::Doctor` + `dispatch` + `handlers/doctor.rs`。
- [x] 8. `cli/tests/architecture_rules.rs` 纳入 `cmd/doctor.rs`。
- [x] 9. `cli/tests/http_doctor_probe.rs`：mockito 覆盖 `probe_openapi_json` 200 / 非 200。
- [x] 10. 运行 `make check` 并修复问题。

## Tasks（v2 方案 B — 服务端聚合）

- [x] 11. `application/system/doctor_service.py` + `TimescaleBarStore.get_positions_detail`。
- [x] 12. `GET /v1/system/doctor` + `dependencies.get_system_doctor_envelope`。
- [x] 13. 扩展 CLI `data.quant`、`--sync-days`、契约 schema / fixture / validate 脚本。
- [x] 14. 单测与契约测试 + `make check`。
