# signal overview 实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增 `hiveflow signal overview` 命令，一次输出所有活跃持仓的信号分类摘要 + 组合级关键指标。

**Architecture:** Application 层新增 `_dominant_state` 辅助函数和 `build_signal_overview` 函数；CLI 层新增 `signal_overview_command`；复用已有的 `build_signal_snapshot`、`build_portfolio_signals`、`pick_leader_symbol` 等基础设施。

**Tech Stack:** Python 3.12, typer, rich, SQLModel, pandas, pytest, uv

---

## Chunk 1: Application 层 + CLI 层 + 测试

### Task 1: Application 层 `build_signal_overview`

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

**背景：**
- `SIGNALS_BY_CATEGORY` 定义了 5 个分类；per-asset 分类只有 trend/risk/confirm/regime（quality 的 4 条信号全是 PORTFOLIO 级）
- 每个 asset 的 per-asset 信号 = snapshot 里 `signal["symbol"] != "PORTFOLIO"` 的 17 条
- `_load_market_context` 已存在，签名：`(settings) -> (close_df, high_df, low_df, volume_df, positions)`
- `build_signal_snapshot(symbol, settings, *, window_bars)` 已存在
- `build_portfolio_signals(settings, *, window_bars)` 已存在

- [ ] **Step 1: 写失败测试**

在 `tests/test_signal_cli.py` 末尾追加：

```python
def test_build_signal_overview_returns_all_positions(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_overview
    payload = build_signal_overview()
    assert {a["symbol"] for a in payload["assets"]} == {"BTC", "ETH", "SOL"}
    for asset in payload["assets"]:
        assert set(asset["category_summary"].keys()) == {"trend", "risk", "confirm", "regime"}
        assert asset["signals_total"] == 17
        assert "triggered_total" in asset
    assert len(payload["portfolio"]["signals"]) == 7
    assert all(s["symbol"] == "PORTFOLIO" for s in payload["portfolio"]["signals"])
    assert "as_of" in payload
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_overview_returns_all_positions -v
```
Expected: FAIL（`build_signal_overview` 不存在）

- [ ] **Step 3: 在 `signals.py` 中实现**

在 `build_signal_category_multi` 函数之后追加以下代码：

```python
_CATEGORY_STATE_PRIORITY: dict[str, list[str]] = {
    "trend":   ["bearish", "bullish", "neutral"],
    "confirm": ["bearish", "bullish", "neutral"],
    "regime":  ["bearish", "bullish", "neutral"],
    "risk":    ["high", "medium", "low"],
}


def _dominant_state(category: str, states: list[str]) -> str:
    """返回分类信号的代表性状态（众数，平局时按严重程度优先）。"""
    from collections import Counter
    counts = Counter(states)
    top_count = counts.most_common(1)[0][1]
    top_states = {s for s, c in counts.items() if c == top_count}
    for priority_state in _CATEGORY_STATE_PRIORITY.get(category, []):
        if priority_state in top_states:
            return priority_state
    # Intentional deviation from spec's reference (which returns states[0]):
    # returning the most-common state is more semantically correct than returning
    # an arbitrary first element when no priority match exists.
    return counts.most_common(1)[0][0]


def build_signal_overview(settings: Settings | None = None) -> dict:
    """所有活跃持仓的信号分类摘要 + 组合级信号。

    assets 按 market_value 降序排列。无持仓时退化为全部非 USDT symbol。
    返回结构：
    {
        "as_of": str,
        "assets": [
            {
                "symbol": str,
                "category_summary": {
                    "trend":   {"state": str, "triggered": int, "total": int},
                    "risk":    {"state": str, "triggered": int, "total": int},
                    "confirm": {"state": str, "triggered": int, "total": int},
                    "regime":  {"state": str, "triggered": int, "total": int},
                },
                "triggered_total": int,
                "signals_total": int,   # per-asset 信号数，通常为 17
            },
            ...
        ],
        "portfolio": {  # build_portfolio_signals 的返回值
            "category": "portfolio",
            "as_of": str,
            "signals": [...],
            "data_window": {...},
        },
    }
    """
    s = settings or Settings()
    close_df, _, _, _, positions = _load_market_context(s)

    active_positions = sorted(
        [p for p in positions if (p.market_value or 0.0) > 0.01],
        key=lambda p: p.market_value or 0.0,
        reverse=True,
    )
    if active_positions:
        symbols = [p.symbol.upper() for p in active_positions]
    else:
        symbols = sorted(col for col in close_df.columns if col != "USDT")

    asset_summaries: list[dict] = []
    as_of = ""
    for sym in symbols:
        snapshot = build_signal_snapshot(sym, settings=s)
        if not as_of:
            as_of = snapshot["as_of"]

        per_asset = [sg for sg in snapshot["signals"] if sg["symbol"] != "PORTFOLIO"]

        cat_summary: dict[str, dict] = {}
        for cat in ("trend", "risk", "confirm", "regime"):
            cat_sigs = [sg for sg in per_asset if sg["category"] == cat]
            if not cat_sigs:
                cat_summary[cat] = {"state": "neutral", "triggered": 0, "total": 0}
                continue
            cat_summary[cat] = {
                "state": _dominant_state(cat, [sg["state"] for sg in cat_sigs]),
                "triggered": sum(1 for sg in cat_sigs if sg["triggered"]),
                "total": len(cat_sigs),
            }

        asset_summaries.append({
            "symbol": sym,
            "category_summary": cat_summary,
            "triggered_total": sum(1 for sg in per_asset if sg["triggered"]),
            "signals_total": len(per_asset),
        })

    return {
        "as_of": as_of,
        "assets": asset_summaries,
        "portfolio": build_portfolio_signals(settings=s),
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_overview_returns_all_positions -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "feat: 新增 build_signal_overview 函数"
```

---

### Task 2: CLI `signal overview` 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_signal_cli.py`

**背景：**
- `cli.py` 已有 `signal_portfolio_command`（参考其结构）
- `_signal_state_label(category, state)` 已存在，返回中文状态名
- `box`、`Table`、`console` 已 import
- `_STATE_STYLE` 目前定义在 `signal_snapshot_command` 函数体内（局部变量），尚无模块级常量；在 `signal_overview_command` 中沿用同样的局部定义模式即可
- 在 `signal_portfolio_command` 函数之后、`signal_snapshot_command` 之前插入新命令

- [ ] **Step 1: 写失败测试**

在 `tests/test_signal_cli.py` 末尾追加：

```python
def test_signal_overview_json_returns_all_positions(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "overview", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert {a["symbol"] for a in payload["assets"]} == {"BTC", "ETH", "SOL"}
    for asset in payload["assets"]:
        assert set(asset["category_summary"].keys()) == {"trend", "risk", "confirm", "regime"}
        assert asset["signals_total"] == 17


def test_signal_overview_json_includes_portfolio(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "overview", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert len(payload["portfolio"]["signals"]) == 7
    assert all(s["symbol"] == "PORTFOLIO" for s in payload["portfolio"]["signals"])


def test_signal_overview_pretty_prints_table(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "overview"])
    assert result.exit_code == 0, result.stdout
    assert "信号总览" in result.stdout
    assert "触发" in result.stdout
    assert "组合" in result.stdout
    assert "状态" in result.stdout


def test_signal_overview_fails_without_market_data(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "no-market.db"
    monkeypatch.setenv("HIVEFLOW_DATABASE_URL", f"sqlite:///{db_path}")
    create_all_tables()
    result = CliRunner().invoke(app, ["signal", "overview", "--output", "json"])
    assert result.exit_code == 1, result.stdout
    payload = json.loads(result.stdout)
    assert "code" in payload
    assert payload["details"]["strict_mode"] is True
    assert payload.get("context") == "signal.snapshot"  # passthrough from underlying error
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_overview_json_returns_all_positions \
  tests/test_signal_cli.py::test_signal_overview_json_includes_portfolio \
  tests/test_signal_cli.py::test_signal_overview_pretty_prints_table \
  tests/test_signal_cli.py::test_signal_overview_fails_without_market_data -v
```
Expected: FAIL（`signal overview` 命令不存在）

- [ ] **Step 3: 更新 `cli.py` imports，添加 `build_signal_overview`**

在 `cli.py` 顶部，找到 signals 的 import 块（目前包含 `build_portfolio_signals`, `build_signal_category` 等），追加 `build_signal_overview`：

```python
from hiveflow.application.signals import (
    SIGNALS_BY_CATEGORY,
    SignalPipelineError,
    build_portfolio_signals,
    build_signal_category,
    build_signal_category_multi,
    build_signal_overview,        # 新增
    build_signal_snapshot,
    pick_leader_symbol,
    signal_keys_of,
)
```

- [ ] **Step 4: 在 `cli.py` 中插入 `signal_overview_command`**

在 `signal_portfolio_command` 函数结束之后、`signal_snapshot_command` 之前插入：

```python
@signal_app.command("overview")
def signal_overview_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出所有持仓资产的信号分类摘要与组合级信号。"""
    try:
        payload = build_signal_overview(settings=Settings())
    except SignalPipelineError as exc:
        _emit_strict_failure(
            code=ErrorCode.SIGNAL_REQUIRED_MISSING,
            message=exc.message,
            details=exc.details,
            hint=exc.hint,
            output=output,
            context=exc.context,
        )
        return

    if output == "json":
        typer.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    console.print(f"\n[bold]信号总览[/bold]  [dim]{payload['as_of']}[/dim]")

    _STATE_STYLE: dict[str, str] = {
        "bullish": "green", "bearish": "red", "neutral": "dim",
        "low": "green", "medium": "yellow", "high": "bold red",
        "good": "green", "warning": "yellow", "bad": "bold red",
    }

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("资产", min_width=6)
    table.add_column("趋势", min_width=6)
    table.add_column("风险", min_width=8)
    table.add_column("确认", min_width=6)
    table.add_column("状态", min_width=6)
    table.add_column("触发/总计", justify="right")

    for asset in payload["assets"]:
        cs = asset["category_summary"]
        row_cells: list[str] = [asset["symbol"]]
        for cat in ("trend", "risk", "confirm", "regime"):
            state = cs[cat]["state"]
            label = _signal_state_label(cat, state)
            style = _STATE_STYLE.get(state, "")
            row_cells.append(f"[{style}]{label}[/{style}]" if style else label)
        row_cells.append(f"{asset['triggered_total']} / {asset['signals_total']}")
        table.add_row(*row_cells)
    console.print(table)

    # 组合摘要行（4 个关键指标）
    port_by_key = {s["signal_key"]: s for s in payload["portfolio"]["signals"]}
    parts: list[str] = []
    for key, label in [
        ("concentration_risk", "集中度"),
        ("correlation_spike", "相关性"),
        ("local_breadth_proxy", "宽度"),
        ("confidence_score", "置信度"),
    ]:
        if key not in port_by_key:
            continue
        sig = port_by_key[key]
        state = sig["state"]
        style = _STATE_STYLE.get(state, "")
        if key == "confidence_score":
            val_str = f"{sig['value']:.2f}"
        else:
            val_str = _signal_state_label(sig["category"], state)
        cell = f"[{style}]{val_str}[/{style}]" if style else val_str
        parts.append(f"{label}:{cell}")
    console.print("[dim]组合  [/dim]" + "  ".join(parts))
```

- [ ] **Step 5: 运行新测试，确认通过**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_overview_json_returns_all_positions \
  tests/test_signal_cli.py::test_signal_overview_json_includes_portfolio \
  tests/test_signal_cli.py::test_signal_overview_pretty_prints_table \
  tests/test_signal_cli.py::test_signal_overview_fails_without_market_data -v
```
Expected: 4 PASS

- [ ] **Step 6: 全量回归**

```bash
uv run python -m pytest -q
```
Expected: 全部通过（330+ passed, 0 failed）

- [ ] **Step 7: Commit**

```bash
git add src/hiveflow/cli.py tests/test_signal_cli.py
git commit -m "feat: 新增 signal overview 命令（持仓信号总览）"
```
