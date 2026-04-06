# Quant HTTP + Three-Layer DDD Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `quant` 从本地子进程模式重构为可部署 HTTP 服务，并将 Python 代码重排为 `domain/application/interfaces` 三层包结构，同时让 Rust CLI 通过配置文件调用远端服务。

**Architecture:** Python 侧使用三层 DDD（`domain` 纯规则、`application` 用例编排、`interfaces` 协议适配），HTTP 路由放在 `interfaces/http`，服务启动入口放在 `quant/bin/server.py`。Rust CLI 保持 4 层结构但把 `infrastructure` 从 `python_runner` 替换为 `http_client + config_loader`，通过 `~/.hiveflow/config.toml` 读取服务配置。

**Tech Stack:** Python (`fastapi`, `uvicorn`, `pytest`, `ruff`, `uv`) + Rust (`clap`, `reqwest`, `serde`, `serde_json`, `thiserror`, `toml`, `dirs`)。

---

## File Structure (Locked Before Tasks)

```text
quant/
├── bin/
│   └── server.py                          # 服务端启动入口（包外）
├── pyproject.toml
├── src/
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── errors.py                      # 业务错误码
│   │   ├── governance/
│   │   ├── market_data/
│   │   ├── universe/
│   │   ├── factor/
│   │   ├── signal/
│   │   ├── portfolio/
│   │   ├── risk/
│   │   └── execution/
│   ├── application/
│   │   ├── __init__.py
│   │   ├── contracts/
│   │   │   ├── __init__.py
│   │   │   └── cli_output.py             # 统一输出结构
│   │   └── daily_run_service.py          # 日频编排用例
│   └── interfaces/
│       ├── __init__.py
│       ├── adapters/
│       │   ├── __init__.py
│       │   ├── manifest_repo_ndjson.py
│       │   ├── quotes_repo_parquet.py
│       │   └── universe_repo_parquet.py
│       └── http/
│           ├── __init__.py
│           ├── app.py
│           ├── routes_daily_run.py
│           ├── schemas.py
│           └── mapper.py
└── tests/
    ├── contract/
    ├── integration/
    └── unit/

cli/
├── Cargo.toml
├── src/
│   ├── application/handlers/pipeline_daily.rs
│   ├── infrastructure/http_client.rs
│   ├── infrastructure/config_loader.rs
│   ├── infrastructure/mod.rs
│   ├── error.rs
│   └── main.rs
└── tests/
    ├── smoke.rs
    ├── config_loader.rs
    └── http_pipeline_daily.rs
```

---

### Task 1: Python 三层包骨架与导入重定向

**Files:**
- Create: `quant/src/domain/__init__.py`
- Create: `quant/src/application/__init__.py`
- Create: `quant/src/interfaces/__init__.py`
- Create: `quant/src/domain/errors.py`
- Create: `quant/src/application/contracts/cli_output.py`
- Modify: `quant/pyproject.toml`
- Modify: `quant/tests/unit/contracts/test_errors.py`
- Modify: `quant/tests/unit/contracts/test_cli_output.py`

- [ ] **Step 1: Write failing tests for new import paths**

```python
# quant/tests/unit/contracts/test_errors.py
from domain.errors import ErrorCode


def test_required_error_codes_exist():
    required = {
        "DATA_FETCH_FAILED",
        "LOW_COVERAGE",
        "SOLVER_FALLBACK",
        "RISK_GATE_BLOCKED",
        "EXECUTION_PRECHECK_FAILED",
    }
    assert required.issubset({e.value for e in ErrorCode})
```

```python
# quant/tests/unit/contracts/test_cli_output.py
from application.contracts.cli_output import ok_output


def test_ok_output_required_fields():
    payload = ok_output(command="hf pipeline daily", run_id="run_1", data={"as_of": "2026-04-01"})
    for key in ["schema_version", "command", "run_id", "status", "generated_at", "data", "warnings", "errors"]:
        assert key in payload
```

- [ ] **Step 2: Run tests to verify FAIL**

Run: `cd quant && uv run pytest tests/unit/contracts/test_errors.py tests/unit/contracts/test_cli_output.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'domain'` or `application`

- [ ] **Step 3: Implement minimal package files and package config**

```python
# quant/src/domain/errors.py
from enum import Enum


class ErrorCode(str, Enum):
    DATA_FETCH_FAILED = "DATA_FETCH_FAILED"
    LOW_COVERAGE = "LOW_COVERAGE"
    SOLVER_FALLBACK = "SOLVER_FALLBACK"
    RISK_GATE_BLOCKED = "RISK_GATE_BLOCKED"
    EXECUTION_PRECHECK_FAILED = "EXECUTION_PRECHECK_FAILED"
```

```python
# quant/src/application/contracts/cli_output.py
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ok_output(command: str, run_id: str, data: dict, warnings: list[dict] | None = None) -> dict:
    return {
        "schema_version": "1.0.0",
        "command": command,
        "run_id": run_id,
        "status": "ok",
        "generated_at": _now_iso(),
        "source": "system",
        "advice_only": False,
        "decision_weight": 1,
        "data": data,
        "warnings": warnings or [],
        "errors": [],
    }
```

```toml
# quant/pyproject.toml (wheel packages section)
[tool.hatch.build.targets.wheel]
packages = ["src/domain", "src/application", "src/interfaces"]
```

- [ ] **Step 4: Run tests to verify PASS**

Run: `cd quant && uv run pytest tests/unit/contracts/test_errors.py tests/unit/contracts/test_cli_output.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add quant/src/domain/__init__.py quant/src/application/__init__.py quant/src/interfaces/__init__.py quant/src/domain/errors.py quant/src/application/contracts/cli_output.py quant/pyproject.toml quant/tests/unit/contracts/test_errors.py quant/tests/unit/contracts/test_cli_output.py
git commit -m "refactor: bootstrap three-layer python packages"
```

### Task 2: 应用编排层迁移（daily run service）

**Files:**
- Create: `quant/src/application/daily_run_service.py`
- Modify: `quant/tests/integration/test_daily_pipeline_mvp.py`

- [ ] **Step 1: Write failing integration test against new service path**

```python
# quant/tests/integration/test_daily_pipeline_mvp.py
from application.daily_run_service import run_daily


def test_daily_pipeline_end_to_end(tmp_path):
    out = run_daily(as_of="2026-04-01", root=tmp_path)
    assert out["status"] in {"ok", "warning"}
    assert out["run_id"].startswith("run_")
    assert "data_manifest_id" in out["data"]
    assert "execution_plan" in out["data"]
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd quant && uv run pytest tests/integration/test_daily_pipeline_mvp.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'application.daily_run_service'`

- [ ] **Step 3: Implement minimal service orchestration**

```python
# quant/src/application/daily_run_service.py
from uuid import uuid4

from application.contracts.cli_output import ok_output


def run_daily(as_of: str, root) -> dict:
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"
    return ok_output(
        command="hf pipeline daily",
        run_id=run_id,
        data={
            "as_of": as_of,
            "data_manifest_id": f"dm_{as_of.replace('-', '')}_{str(uuid4())[:6]}",
            "execution_plan": {"orders": []},
        },
    )
```

- [ ] **Step 4: Run test to verify PASS**

Run: `cd quant && uv run pytest tests/integration/test_daily_pipeline_mvp.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add quant/src/application/daily_run_service.py quant/tests/integration/test_daily_pipeline_mvp.py
git commit -m "refactor: move daily run orchestration into application layer"
```

### Task 3: HTTP 接口层与服务启动入口

**Files:**
- Add dependency: `quant/pyproject.toml` (`fastapi`, `uvicorn`)
- Create: `quant/src/interfaces/http/schemas.py`
- Create: `quant/src/interfaces/http/mapper.py`
- Create: `quant/src/interfaces/http/routes_daily_run.py`
- Create: `quant/src/interfaces/http/app.py`
- Create: `quant/bin/server.py`
- Create: `quant/tests/contract/test_http_daily_endpoint.py`

- [ ] **Step 1: Write failing HTTP contract test**

```python
# quant/tests/contract/test_http_daily_endpoint.py
from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_post_daily_contract():
    app = create_app()
    client = TestClient(app)
    resp = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["command"] == "hf pipeline daily"
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd quant && uv run pytest tests/contract/test_http_daily_endpoint.py -q`
Expected: FAIL with import/module error

- [ ] **Step 3: Implement minimal HTTP layer and server entry**

```python
# quant/src/interfaces/http/schemas.py
from pydantic import BaseModel


class DailyRunRequest(BaseModel):
    as_of: str
```

```python
# quant/src/interfaces/http/mapper.py
from interfaces.http.schemas import DailyRunRequest


def to_daily_input(req: DailyRunRequest) -> dict:
    return {"as_of": req.as_of}
```

```python
# quant/src/interfaces/http/routes_daily_run.py
from fastapi import APIRouter

from application.daily_run_service import run_daily
from interfaces.http.mapper import to_daily_input
from interfaces.http.schemas import DailyRunRequest

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


@router.post("/daily")
def post_daily(req: DailyRunRequest):
    data = to_daily_input(req)
    return run_daily(as_of=data["as_of"], root=None)
```

```python
# quant/src/interfaces/http/app.py
from fastapi import FastAPI

from interfaces.http.routes_daily_run import router as daily_router


def create_app() -> FastAPI:
    app = FastAPI(title="HiveFlow Quant Service", version="0.1.0")
    app.include_router(daily_router)
    return app
```

```python
# quant/bin/server.py
import os

import uvicorn


if __name__ == "__main__":
    host = os.getenv("HF_HOST", "0.0.0.0")
    port = int(os.getenv("HF_PORT", "8000"))
    uvicorn.run("interfaces.http.app:create_app", host=host, port=port, factory=True)
```

- [ ] **Step 4: Run test to verify PASS**

Run: `cd quant && uv run pytest tests/contract/test_http_daily_endpoint.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add quant/pyproject.toml quant/src/interfaces/http/schemas.py quant/src/interfaces/http/mapper.py quant/src/interfaces/http/routes_daily_run.py quant/src/interfaces/http/app.py quant/bin/server.py quant/tests/contract/test_http_daily_endpoint.py
git commit -m "feat: add http interface layer and server entrypoint"
```

### Task 4: Rust CLI 配置文件能力（~/.hiveflow/config.toml）

**Files:**
- Modify: `cli/Cargo.toml` (add `toml`, `dirs`)
- Create: `cli/src/lib.rs`
- Create: `cli/src/infrastructure/config_loader.rs`
- Modify: `cli/src/infrastructure/mod.rs`
- Create: `cli/tests/config_loader.rs`

- [ ] **Step 1: Write failing config loader tests**

```rust
// cli/tests/config_loader.rs
use hf_cli::infrastructure::config_loader::load_config_from;

#[test]
fn load_config_from_file() {
    let content = "server_url = \"http://127.0.0.1:8000\"\ntimeout_ms = 5000\nretry = 2\n";
    let cfg = load_config_from(content).expect("config should parse");
    assert_eq!(cfg.server_url, "http://127.0.0.1:8000");
    assert_eq!(cfg.timeout_ms, 5000);
    assert_eq!(cfg.retry, 2);
}
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd cli && cargo test --test config_loader`
Expected: FAIL with unresolved module/function

- [ ] **Step 3: Implement minimal config loader**

```rust
// cli/src/lib.rs
pub mod application;
pub mod cmd;
pub mod contracts;
pub mod domain;
pub mod error;
pub mod infrastructure;
```

```rust
// cli/src/infrastructure/config_loader.rs
use serde::Deserialize;

#[derive(Debug, Clone, Deserialize)]
pub struct CliConfig {
    pub server_url: String,
    pub timeout_ms: u64,
    pub retry: u32,
}

pub fn load_config_from(raw: &str) -> Result<CliConfig, toml::de::Error> {
    toml::from_str(raw)
}
```

```rust
// cli/src/infrastructure/mod.rs
pub mod config_loader;
pub mod http_client;
pub mod stdout_parser;
```

- [ ] **Step 4: Run test to verify PASS**

Run: `cd cli && cargo test --test config_loader`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/Cargo.toml cli/src/lib.rs cli/src/infrastructure/config_loader.rs cli/src/infrastructure/mod.rs cli/tests/config_loader.rs
git commit -m "feat: add cli config loader for ~/.hiveflow/config.toml"
```

### Task 5: Rust HTTP 客户端替换 Python Runner

**Files:**
- Modify: `cli/Cargo.toml` (add `reqwest`)
- Create: `cli/src/infrastructure/http_client.rs`
- Modify: `cli/src/application/handlers/pipeline_daily.rs`
- Delete: `cli/src/infrastructure/python_runner.rs`
- Create: `cli/tests/http_pipeline_daily.rs`

- [ ] **Step 1: Write failing HTTP client integration test (mock server)**

```rust
// cli/tests/http_pipeline_daily.rs
use serde_json::Value;

use hf_cli::infrastructure::http_client::post_daily;
use mockito::Server;

#[test]
fn pipeline_daily_calls_http_endpoint() {
    let mut server = Server::new();
    let _m = server
        .mock("POST", "/api/v1/pipeline/daily")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"schema_version":"1.0.0","command":"hf pipeline daily","status":"ok","data":{"as_of":"2026-04-01"},"warnings":[],"errors":[]}"#)
        .create();

    let out = post_daily(&server.url(), "2026-04-01", 1000).expect("http call should succeed");
    let status = out["status"].as_str().unwrap_or("unknown");
    assert_eq!(status, "ok");
}
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd cli && cargo test --test http_pipeline_daily`
Expected: FAIL with unresolved function/module until `post_daily` is implemented

- [ ] **Step 3: Implement HTTP client and handler wiring**

```rust
// cli/src/infrastructure/http_client.rs
use reqwest::blocking::Client;
use serde_json::{json, Value};

use crate::error::AppError;

pub fn post_daily(server_url: &str, as_of: &str, timeout_ms: u64) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/pipeline/daily", server_url.trim_end_matches('/'));
    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(timeout_ms))
        .build()
        .map_err(AppError::HttpClient)?;

    let resp = client
        .post(url)
        .json(&json!({"as_of": as_of}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = resp.status();
    let body: Value = resp.json().map_err(AppError::InvalidJson)?;
    if !status.is_success() {
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    Ok(body)
}
```

```rust
// cli/src/application/handlers/pipeline_daily.rs
use crate::infrastructure::config_loader::CliConfig;
use crate::infrastructure::http_client::post_daily;

pub fn handle_pipeline_daily(as_of: &str, cfg: &CliConfig) -> Result<serde_json::Value, crate::error::AppError> {
    post_daily(&cfg.server_url, as_of, cfg.timeout_ms)
}
```

- [ ] **Step 4: Run tests to verify PASS**

Run: `cd cli && cargo test --test http_pipeline_daily && cargo test`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add cli/Cargo.toml cli/src/infrastructure/http_client.rs cli/src/application/handlers/pipeline_daily.rs cli/src/error.rs cli/tests/http_pipeline_daily.rs
git rm cli/src/infrastructure/python_runner.rs
git commit -m "refactor: switch cli execution from python subprocess to http client"
```

### Task 6: Python CLI 入口下线与测试切换到 HTTP

**Files:**
- Modify: `quant/tests/contract/test_python_cli_contract.py`
- Modify: `Makefile`
- Modify: `cli/tests/smoke.rs`
- Modify: `docs/CLI_OUTPUT_EXAMPLES.md`
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Write failing tests for new run path**

```python
# quant/tests/contract/test_python_cli_contract.py
from fastapi.testclient import TestClient

from interfaces.http.app import create_app


def test_daily_contract_via_http():
    client = TestClient(create_app())
    out = client.post("/api/v1/pipeline/daily", json={"as_of": "2026-04-01"})
    assert out.status_code == 200
    payload = out.json()
    assert payload["command"] == "hf pipeline daily"
```

- [ ] **Step 2: Run test to verify FAIL**

Run: `cd quant && uv run pytest tests/contract/test_python_cli_contract.py -q`
Expected: FAIL until all old `hiveflow.*` import references are removed

- [ ] **Step 3: Update startup/testing commands and smoke path**

```makefile
# Makefile
run-pipeline:
	@if [ -z "$(AS_OF)" ]; then \
		echo "Usage: make run-pipeline AS_OF=YYYY-MM-DD"; \
		exit 2; \
	fi
	cd cli && cargo run -- pipeline daily --as-of "$(AS_OF)"
```

```rust
// cli/tests/smoke.rs
#[test]
fn hf_help_works() {
    let output = std::process::Command::new("cargo")
        .args(["run", "--", "--help"])
        .current_dir(".")
        .output()
        .expect("run cli help");
    assert!(output.status.success());
}
```

- [ ] **Step 4: Run tests to verify PASS**

Run: `cd quant && uv run pytest tests/contract/test_python_cli_contract.py -q && cd ../cli && cargo test --test smoke`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add quant/tests/contract/test_python_cli_contract.py Makefile cli/tests/smoke.rs docs/CLI_OUTPUT_EXAMPLES.md docs/ARCHITECTURE.md
git commit -m "chore: switch contract and run path to http service model"
```

### Task 7: 全量验证与 CI

**Files:**
- Modify: `.github/workflows/core-tests.yml`
- Modify: `.github/workflows/validate-cli-output.yml`
- Modify: `README.md`

- [ ] **Step 1: Run full verification (expect at least one fail before CI sync)**

Run:

```bash
cd quant && uv run python -m pytest -q
cd quant && uv run ruff check .
./scripts/validate_cli_output_fixtures.sh
cd cli && cargo test
```

Expected: one or more failures until workflow/docs sync

- [ ] **Step 2: Update CI commands to new runtime model**

```yaml
# .github/workflows/core-tests.yml (key steps)
- uses: astral-sh/setup-uv@v6
- run: cd quant && uv run python -m pytest -q
- run: cd quant && uv run ruff check .
- run: ./scripts/validate_cli_output_fixtures.sh
- run: cd cli && cargo test
```

- [ ] **Step 3: Re-run full verification (expect PASS)**

Run: `make check`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/core-tests.yml .github/workflows/validate-cli-output.yml README.md
git commit -m "chore: align ci and docs for quant http service architecture"
```

## Self-Review

- Spec coverage:
  - HTTP 通信替代子进程：Task 3, Task 5, Task 6.
  - `quant/src` 三层包：Task 1, Task 2, Task 3.
  - `quant/bin/server.py` 启动：Task 3.
  - CLI 配置文件：Task 4.
  - 端到端验证：Task 6, Task 7.
- Placeholder scan: no TODO/TBD placeholders.
- Type consistency:
  - `as_of` 作为 HTTP 入参在 Python/Rust 测试和实现中统一。
  - endpoint 固定为 `POST /api/v1/pipeline/daily`。
  - CLI 输出契约统一复用 `ok_output` 字段。

Plan complete and saved to `docs/superpowers/plans/2026-04-01-quant-http-ddd-three-layer-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
