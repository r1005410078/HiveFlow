# Signal 显式 Symbol 重构实现计划

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `signal` 命令从"自动选 leader"改为"显式指定 symbol"，同时新增 `signal portfolio`（组合级信号）和无 `--symbol` 时多资产并排输出能力。

**Architecture:** Application 层新增 `pick_leader_symbol` / `build_portfolio_signals` / `build_signal_category_multi`；`build_signal_snapshot` 和 `build_signal_category` 改为接受显式 `symbol: str`；CLI 层 `signal snapshot` 的 `--symbol` 变为必填，`signal trend/risk/confirm/regime/quality` 的 `--symbol` 为可选（缺省时对所有持仓各输出一行）；`context daily` 在调用 `build_signal_snapshot` 前先调用 `pick_leader_symbol`。

**Tech Stack:** Python 3.12, typer, SQLModel, pandas, pytest, uv

---

## Chunk 1: Application Layer

### Task 1: 为 `build_signal_snapshot` 添加显式 `symbol` 参数

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试——直接以 `symbol` 参数调用 `build_signal_snapshot`**

```python
# tests/test_signal_cli.py — 在文件末尾追加

def test_build_signal_snapshot_accepts_explicit_symbol(tmp_path, monkeypatch) -> None:
    """build_signal_snapshot 应接受显式 symbol 参数。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_snapshot
    payload = build_signal_snapshot("BTC")
    assert payload["symbol"] == "BTC"
    assert len(payload["signals"]) == 24


def test_build_signal_snapshot_raises_on_unknown_symbol(tmp_path, monkeypatch) -> None:
    """build_signal_snapshot 对不存在的 symbol 应抛出 SignalPipelineError。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_snapshot, SignalPipelineError
    with pytest.raises(SignalPipelineError) as exc_info:
        build_signal_snapshot("XYZ_NOT_EXIST")
    assert "symbol_not_found" in str(exc_info.value.details)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_snapshot_accepts_explicit_symbol \
  tests/test_signal_cli.py::test_build_signal_snapshot_raises_on_unknown_symbol -v
```
Expected: FAIL（`build_signal_snapshot` 暂不接受位置参数）

- [ ] **Step 3: 修改 `build_signal_snapshot` 签名，添加 `symbol: str` 为第一个必填参数**

在 `src/hiveflow/application/signals.py` 中：

```python
# 修改前：
def build_signal_snapshot(
    settings: Settings | None = None,
    *,
    window_bars: int | None = None,
) -> dict:

# 修改后：
def build_signal_snapshot(
    symbol: str,
    settings: Settings | None = None,
    *,
    window_bars: int | None = None,
) -> dict:
```

然后删除函数体内 `leader = _leader_symbol(close_df, positions)` 这一行，改为：

```python
    symbol = symbol.upper()
    if symbol not in close_df.columns:
        raise _fail(
            context="signal.snapshot",
            message=f"Symbol {symbol!r} 在 MarketBar 中无数据，严格模式中断。",
            details={
                "strict_mode": True,
                "symbol": symbol,
                "available_symbols": sorted(close_df.columns.tolist()),
                "reason": "symbol_not_found",
            },
            hint={"action": "check_market_data", "run": "hiveflow market-data list"},
        )
```

函数体内所有 `leader` 变量全部替换为 `symbol`。同时：
- 在 `return` dict 中，`"symbol": leader` → `"symbol": symbol`
- 注意 `_leader_symbol` 函数本身暂时**保留**（Task 2 会新增 `pick_leader_symbol` 调用它）

- [ ] **Step 4: 运行新测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_snapshot_accepts_explicit_symbol \
  tests/test_signal_cli.py::test_build_signal_snapshot_raises_on_unknown_symbol -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "refactor: build_signal_snapshot 改为接受显式 symbol 参数"
```

---

### Task 2: 新增公开函数 `pick_leader_symbol`

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_pick_leader_symbol_returns_max_market_value_position(tmp_path, monkeypatch) -> None:
    """pick_leader_symbol 应返回 market_value 最大的持仓 symbol。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import pick_leader_symbol
    leader = pick_leader_symbol()
    assert leader == "BTC"  # _seed_market_and_positions 里 BTC market_value=800 最大
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_pick_leader_symbol_returns_max_market_value_position -v
```
Expected: FAIL（`pick_leader_symbol` 不存在）

- [ ] **Step 3: 在 `signals.py` 中新增 `pick_leader_symbol`**

紧接在 `_leader_symbol` 函数定义之后添加：

```python
def pick_leader_symbol(settings: Settings | None = None) -> str:
    """从持仓和 MarketBar 中选出市值最大的资产 symbol。

    无持仓时退化为 MarketBar 中按字母排序的第一个非 USDT symbol。
    """
    close_df, _, _, _, positions = _load_market_context(settings or Settings())
    return _leader_symbol(close_df, positions)
```

同时在文件顶部的导出列表（如果有 `__all__`）或 cli.py 的 import 中，稍后步骤会使用此函数。

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_pick_leader_symbol_returns_max_market_value_position -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "feat: 新增 pick_leader_symbol 公开函数"
```

---

### Task 3: 更新 `build_signal_category` 接受显式 `symbol`

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_build_signal_category_accepts_explicit_symbol(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_category
    payload = build_signal_category("trend", "ETH")
    assert payload["symbol"] == "ETH"
    assert payload["category"] == "trend"
    assert len(payload["signals"]) == 6
    assert all(s["symbol"] == "ETH" for s in payload["signals"])
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_category_accepts_explicit_symbol -v
```

- [ ] **Step 3: 修改 `build_signal_category` 签名**

```python
# 修改前：
def build_signal_category(category: str, settings: Settings | None = None) -> dict:
    ...
    snapshot = build_signal_snapshot(settings=settings)

# 修改后：
def build_signal_category(category: str, symbol: str, settings: Settings | None = None) -> dict:
    ...
    snapshot = build_signal_snapshot(symbol, settings=settings)
```

注意返回的 `"symbol"` 字段现在是 `snapshot["symbol"]`，即 `symbol.upper()`。

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_category_accepts_explicit_symbol -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "refactor: build_signal_category 改为接受显式 symbol 参数"
```

---

### Task 4: 新增 `build_portfolio_signals`

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_build_portfolio_signals_returns_7_portfolio_signals(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_portfolio_signals
    payload = build_portfolio_signals()
    assert payload["category"] == "portfolio"
    assert "as_of" in payload
    assert len(payload["signals"]) == 7
    assert all(s["symbol"] == "PORTFOLIO" for s in payload["signals"])
    expected_keys = {
        "concentration_risk", "correlation_spike", "local_breadth_proxy",
        "data_freshness", "data_completeness", "signal_stability", "confidence_score",
    }
    assert {s["signal_key"] for s in payload["signals"]} == expected_keys
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_portfolio_signals_returns_7_portfolio_signals -v
```

- [ ] **Step 3: 新增 `build_portfolio_signals`**

在 `signals.py` 的 `build_signal_category` 函数之后添加：

```python
def build_portfolio_signals(
    settings: Settings | None = None,
    *,
    window_bars: int | None = None,
) -> dict:
    """输出组合级别信号（7 个 symbol='PORTFOLIO' 的信号）。

    内部使用 pick_leader_symbol 选取主资产运行完整快照，
    再过滤出 PORTFOLIO 级别信号返回。
    """
    leader = pick_leader_symbol(settings)
    snapshot = build_signal_snapshot(leader, settings=settings, window_bars=window_bars)
    portfolio_sigs = [s for s in snapshot["signals"] if s["symbol"] == "PORTFOLIO"]
    return {
        "category": "portfolio",
        "as_of": snapshot["as_of"],
        "signals": portfolio_sigs,
        "data_window": snapshot["data_window"],
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_portfolio_signals_returns_7_portfolio_signals -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "feat: 新增 build_portfolio_signals 函数"
```

---

### Task 5: 新增 `build_signal_category_multi`（多资产并排）

**Files:**
- Modify: `src/hiveflow/application/signals.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_build_signal_category_multi_returns_all_positions(tmp_path, monkeypatch) -> None:
    """无 symbol 时应对所有持仓各计算一次分类信号。"""
    _seed_market_and_positions(tmp_path, monkeypatch)
    from hiveflow.application.signals import build_signal_category_multi
    payload = build_signal_category_multi("trend")
    assert payload["category"] == "trend"
    assert set(payload["symbols"]) == {"BTC", "ETH", "SOL"}
    assert set(payload["signals_by_symbol"].keys()) == {"BTC", "ETH", "SOL"}
    for sym in ("BTC", "ETH", "SOL"):
        sigs = payload["signals_by_symbol"][sym]
        assert len(sigs) == 6
        assert all(s["category"] == "trend" for s in sigs)
        assert all(s["symbol"] == sym for s in sigs)
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_category_multi_returns_all_positions -v
```

- [ ] **Step 3: 新增 `build_signal_category_multi`**

在 `build_portfolio_signals` 之后添加：

```python
def build_signal_category_multi(
    category: str,
    settings: Settings | None = None,
) -> dict:
    """对所有活跃持仓（market_value > 0.01）分别计算指定分类的信号。

    无持仓时退化为 MarketBar 中全部非 USDT symbol。
    返回格式：{"category": ..., "symbols": [...], "signals_by_symbol": {...}}
    """
    if category not in SIGNALS_BY_CATEGORY:
        raise _fail(
            context=f"signal.{category}",
            message=f"未知信号分类 {category!r}。",
            details={"valid_categories": list(SIGNALS_BY_CATEGORY.keys())},
        )
    s = settings or Settings()
    close_df, _, _, _, positions = _load_market_context(s)

    active = [
        p.symbol.upper()
        for p in positions
        if (p.market_value or 0.0) > 0.01
    ]
    if not active:
        active = sorted(col for col in close_df.columns if col != "USDT")

    signals_by_symbol: dict[str, list[dict]] = {}
    for sym in active:
        snapshot = build_signal_snapshot(sym, settings=s)
        signals_by_symbol[sym] = [sg for sg in snapshot["signals"] if sg["category"] == category]

    return {
        "category": category,
        "symbols": active,
        "signals_by_symbol": signals_by_symbol,
    }
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py::test_build_signal_category_multi_returns_all_positions -v
```

- [ ] **Step 5: 全量 application 层回归**

```bash
uv run python -m pytest tests/test_signal_cli.py -q
```
Expected: 全部通过（测试数 >= 31）

- [ ] **Step 6: Commit**

```bash
git add src/hiveflow/application/signals.py tests/test_signal_cli.py
git commit -m "feat: 新增 build_signal_category_multi 函数"
```

---

## Chunk 2: CLI Layer

### Task 6: `signal snapshot` 改为 `--symbol` 必填

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_signal_snapshot_with_explicit_symbol_succeeds(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "snapshot", "--symbol", "BTC", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["symbol"] == "BTC"
    assert len(payload["signals"]) == 24


def test_signal_snapshot_without_symbol_fails(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "snapshot", "--output", "json"])
    # typer 对必填 Option 缺失返回 exit_code=2
    assert result.exit_code == 2
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_snapshot_with_explicit_symbol_succeeds \
  tests/test_signal_cli.py::test_signal_snapshot_without_symbol_fails -v
```

- [ ] **Step 3: 修改 `signal_snapshot_command`**

在 `cli.py` 中更新：

```python
# 1. 在 cli.py 顶部 imports 中，补充 pick_leader_symbol（Task 9 用），
#    以及 build_portfolio_signals / build_signal_category_multi（Task 7/8 用）
from hiveflow.application.signals import (
    SIGNALS_BY_CATEGORY,
    SignalPipelineError,
    build_portfolio_signals,
    build_signal_category,
    build_signal_category_multi,
    build_signal_snapshot,
    pick_leader_symbol,
    signal_keys_of,
)

# 2. signal_snapshot_command 函数签名改为：
@signal_app.command("snapshot")
def signal_snapshot_command(
    symbol: str = typer.Option(..., "--symbol", "-s", help="目标资产 symbol，如 BTC"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出指定资产的聚合信号快照（含组合级信号）。"""
    app_settings = Settings()
    try:
        payload = build_signal_snapshot(symbol.upper(), settings=app_settings)
    except SignalPipelineError as exc:
        ...  # 保持原有错误处理不变
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_snapshot_with_explicit_symbol_succeeds \
  tests/test_signal_cli.py::test_signal_snapshot_without_symbol_fails -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/cli.py tests/test_signal_cli.py
git commit -m "feat: signal snapshot 改为 --symbol 必填"
```

---

### Task 7: 为 `signal trend/risk/confirm/regime/quality` 添加可选 `--symbol`

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_signal_trend_with_symbol_outputs_single_asset(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "trend", "--symbol", "ETH", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["symbol"] == "ETH"
    assert payload["category"] == "trend"
    assert len(payload["signals"]) == 6
    assert all(s["symbol"] == "ETH" for s in payload["signals"])


def test_signal_trend_without_symbol_outputs_all_positions(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "trend", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["category"] == "trend"
    assert set(payload["symbols"]) == {"BTC", "ETH", "SOL"}
    for sym in ("BTC", "ETH", "SOL"):
        assert len(payload["signals_by_symbol"][sym]) == 6
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_trend_with_symbol_outputs_single_asset \
  tests/test_signal_cli.py::test_signal_trend_without_symbol_outputs_all_positions -v
```

- [ ] **Step 3: 修改所有五个分类命令（trend/risk/confirm/regime/quality）**

以 `signal_trend_command` 为例，其他四个同理：

```python
@signal_app.command("trend")
def signal_trend_command(
    symbol: str | None = typer.Option(None, "--symbol", "-s", help="目标资产 symbol；不指定则输出所有持仓"),
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出趋势类信号。"""
    try:
        if symbol:
            payload = build_signal_category("trend", symbol.upper(), settings=Settings())
        else:
            payload = build_signal_category_multi("trend", settings=Settings())
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

    # pretty 模式：单资产沿用原表格；多资产加一列 symbol
    if symbol:
        # 原有渲染逻辑不变（表格列：信号键 | 状态 | 数值 | 触发）
        table = Table("信号键", "状态", "数值", "触发", title=f"趋势信号 [{payload['symbol']}]")
        for item in payload["signals"]:
            table.add_row(
                _signal_key_label(item["signal_key"]),
                _signal_state_label(item["category"], item["state"]),
                str(item["value"]),
                "✓" if item["triggered"] else "-",
            )
    else:
        # 多资产：加 symbol 列
        table = Table("资产", "信号键", "状态", "数值", "触发", title="趋势信号（所有持仓）")
        for sym in payload["symbols"]:
            for item in payload["signals_by_symbol"][sym]:
                table.add_row(
                    sym,
                    _signal_key_label(item["signal_key"]),
                    _signal_state_label(item["category"], item["state"]),
                    str(item["value"]),
                    "✓" if item["triggered"] else "-",
                )
    console.print(table)
```

对 `signal_risk_command`、`signal_confirm_command`、`signal_regime_command`、`signal_quality_command` 做相同修改（分类名称和标题各自对应即可）。

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_trend_with_symbol_outputs_single_asset \
  tests/test_signal_cli.py::test_signal_trend_without_symbol_outputs_all_positions -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/cli.py tests/test_signal_cli.py
git commit -m "feat: signal category 命令新增可选 --symbol，缺省时输出所有持仓"
```

---

### Task 8: 新增 `signal portfolio` 命令

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_signal_cli.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_signal_cli.py — 追加

def test_signal_portfolio_json_outputs_7_portfolio_signals(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "portfolio", "--output", "json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["category"] == "portfolio"
    assert "as_of" in payload
    assert len(payload["signals"]) == 7
    assert all(s["symbol"] == "PORTFOLIO" for s in payload["signals"])
    expected_keys = {
        "concentration_risk", "correlation_spike", "local_breadth_proxy",
        "data_freshness", "data_completeness", "signal_stability", "confidence_score",
    }
    assert {s["signal_key"] for s in payload["signals"]} == expected_keys


def test_signal_portfolio_pretty_prints_table(tmp_path, monkeypatch) -> None:
    _seed_market_and_positions(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["signal", "portfolio"])
    assert result.exit_code == 0, result.stdout
    assert "信号键" in result.stdout
    assert "状态" in result.stdout
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_portfolio_json_outputs_7_portfolio_signals \
  tests/test_signal_cli.py::test_signal_portfolio_pretty_prints_table -v
```

- [ ] **Step 3: 在 `cli.py` 中新增 `signal portfolio` 命令**

在 `signal_quality_command` 之后，`signal_snapshot_command` 之前，添加：

```python
@signal_app.command("portfolio")
def signal_portfolio_command(
    output: str = typer.Option("pretty", "--output", "-o", callback=_validate_output_format),
) -> None:
    """输出组合级别信号（集中度、相关性、市场广度、数据质量等）。"""
    try:
        payload = build_portfolio_signals(settings=Settings())
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

    table = Table("信号键", "分类", "状态", "数值", "触发", title="组合级别信号")
    for item in payload["signals"]:
        table.add_row(
            _signal_key_label(item["signal_key"]),
            item["category"],
            _signal_state_label(item["category"], item["state"]),
            str(item["value"]),
            "✓" if item["triggered"] else "-",
        )
    console.print(table)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
uv run python -m pytest \
  tests/test_signal_cli.py::test_signal_portfolio_json_outputs_7_portfolio_signals \
  tests/test_signal_cli.py::test_signal_portfolio_pretty_prints_table -v
```

- [ ] **Step 5: Commit**

```bash
git add src/hiveflow/cli.py tests/test_signal_cli.py
git commit -m "feat: 新增 signal portfolio 命令（组合级别信号）"
```

---

### Task 9: `context daily` 改为显式传入 leader symbol

**Files:**
- Modify: `src/hiveflow/cli.py`
- Test: `tests/test_signal_cli.py`（现有 context daily 测试应继续通过，无需新增）

- [ ] **Step 1: 确认现有 context daily 测试在修改前仍通过**

```bash
uv run python -m pytest tests/test_signal_cli.py -k "context_daily" -q
```
Expected: PASS（此时 context daily 内部还在用旧签名，但 build_signal_snapshot 已改签名，所以这步会 FAIL——这是预期的，说明 Task 9 确实必要）

- [ ] **Step 2: 修改 `context_daily_command` 中的 `build_signal_snapshot` 调用**

找到 `context_daily_command` 函数中所有 `build_signal_snapshot(settings=app_settings, ...)` 调用。在循环开始之前添加 leader 计算（约在窗口循环逻辑之前）：

```python
# 在 "for size in window_sizes:" 之前添加：
try:
    leader = pick_leader_symbol(settings=app_settings)
except SignalPipelineError as exc:
    _emit_strict_failure(
        code=ErrorCode.SIGNAL_REQUIRED_MISSING,
        message=exc.message,
        details=exc.details,
        hint=exc.hint,
        output=output,
        context="context.daily",
    )
    return

# 然后将循环内的：
win_signal = build_signal_snapshot(settings=app_settings, window_bars=size)
# 改为：
win_signal = build_signal_snapshot(leader, settings=app_settings, window_bars=size)
```

- [ ] **Step 3: 运行 context daily 测试，确认通过**

```bash
uv run python -m pytest tests/test_signal_cli.py -k "context_daily" -q
```
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add src/hiveflow/cli.py
git commit -m "refactor: context daily 改为显式传入 leader symbol"
```

---

## Chunk 3: Tests 更新与补全

### Task 10: 修复因签名变更而失败的现有测试

**Files:**
- Modify: `tests/test_signal_cli.py`

现有受影响的测试（`--symbol` 变为必填后会出现 exit_code=2）：

- `test_signal_snapshot_json_returns_strict_failure_and_writes_system_log`：需要加 `"--symbol", "BTC"`
- `test_signal_snapshot_json_success_with_seed_data`：需要加 `"--symbol", "BTC"`
- `test_signal_trend_json_outputs_only_trend_category`：需要加 `"--symbol", "BTC"`
- `test_signal_trend_pretty_table_headers_are_chinese`：需要加 `"--symbol", "BTC"`
- `test_signal_snapshot_history_and_show_json`：需要加 `"--symbol", "BTC"` 到 snapshot 调用

- [ ] **Step 1: 运行当前测试，确认哪些失败**

```bash
uv run python -m pytest tests/test_signal_cli.py -q 2>&1 | grep -E "FAILED|ERROR"
```

- [ ] **Step 2: 逐一修复失败测试**

对 `test_signal_snapshot_json_returns_strict_failure_and_writes_system_log`：
```python
# 修改前：
result = runner.invoke(app, ["signal", "snapshot", "--output", "json"])
# 修改后：
result = runner.invoke(app, ["signal", "snapshot", "--symbol", "BTC", "--output", "json"])
```

对 `test_signal_snapshot_json_success_with_seed_data`：
```python
result = runner.invoke(app, ["signal", "snapshot", "--symbol", "BTC", "--output", "json"])
```

对 `test_signal_trend_json_outputs_only_trend_category`：
```python
result = runner.invoke(app, ["signal", "trend", "--symbol", "BTC", "--output", "json"])
```

对 `test_signal_trend_pretty_table_headers_are_chinese`：
```python
result = runner.invoke(app, ["signal", "trend", "--symbol", "BTC"])
```

对 `test_signal_snapshot_history_and_show_json`：
```python
snapshot_result = runner.invoke(app, ["signal", "snapshot", "--symbol", "BTC", "--output", "json"])
```

对 `test_context_daily_json_success_with_latest_snapshots`（调用 `signal snapshot` 的那行）：
```python
signal_result = runner.invoke(app, ["signal", "snapshot", "--symbol", "BTC", "--output", "json"])
```

其他引用 `signal snapshot` 的 context daily 测试同理。

- [ ] **Step 3: 运行全量信号测试**

```bash
uv run python -m pytest tests/test_signal_cli.py -q
```
Expected: 全部通过（测试数 >= 40）

- [ ] **Step 4: Commit**

```bash
git add tests/test_signal_cli.py
git commit -m "test: 修复因 --symbol 必填变更受影响的测试"
```

---

### Task 11: 全量回归

**Files:** 无新增

- [ ] **Step 1: 运行完整测试套件**

```bash
uv run python -m pytest -q
```
Expected: 全部通过（基线 280+ passed，0 failed）

- [ ] **Step 2: 如有失败，定位并修复**

优先排查：
- `tests/test_cli.py`：是否有其他命令调用 `build_signal_snapshot` 或 `build_signal_category` 未传 symbol
- `tests/test_context*`：context daily 相关

- [ ] **Step 3: Commit（如有修复）**

```bash
git add -A
git commit -m "fix: 回归测试修复"
```

- [ ] **Step 4: 最终提交总结**

```bash
git log --oneline -8
```

确认本次重构的所有 commit 整洁可追溯。
