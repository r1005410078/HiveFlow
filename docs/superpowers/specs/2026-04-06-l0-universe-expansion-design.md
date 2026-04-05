# L0 标的池扩展 + 交易日历守卫 设计

> 日期：2026-04-06
> 状态：待实现
> 前置：L5 Phase 1（风险门控已合入 master）
> 范围：精选 28 只标的（6 行业）+ 行业映射集中管理 + daily pipeline 非交易日守卫

---

## 1. 目标

1. **扩展标的池**：从 5 只扩到 28 只，覆盖新能源、机器人、半导体、PCB、电力、电网 6 个行业，每行业 4–6 只，使 L3 行业中性化、L4 行业约束、L5 行业集中度检查具有实质意义。
2. **集中行业映射**：消除 `optimizer_service.py`、`risk_gate_service.py`、`signal_engineering_service.py` 中三份重复的 `_INDUSTRY_MAP`，统一到配置文件 + loader 函数。
3. **交易日历守卫**：daily pipeline 在非交易日（周末/节假日）直接返回 `skipped`，不触发任何计算。

### 明确不做

- 不改 `csi300.txt` / `follow.txt` / `self_select.txt`
- 不引入 `universe_name` 参数到 HTTP 接口（YAGNI）
- 不新增 contract/integration 测试（已有覆盖，新增逻辑足够简单）

---

## 2. 标的池

### 2.1 `default.txt`（28 只）

| 行业 | 代码 | 简称 |
|------|------|------|
| new_energy | 300750.SZ | 宁德时代 |
| new_energy | 002594.SZ | 比亚迪 |
| new_energy | 601012.SH | 隆基绿能 |
| new_energy | 688599.SH | 天合光能 |
| robotics | 300024.SZ | 机器人 |
| robotics | 300124.SZ | 汇川技术 |
| robotics | 002747.SZ | 埃斯顿 |
| robotics | 688015.SH | 奥普特 |
| robotics | 603486.SH | 科沃斯 |
| robotics | 002230.SZ | 科大讯飞 |
| semiconductor | 688041.SH | 中芯国际 |
| semiconductor | 603501.SH | 韦尔股份 |
| semiconductor | 002049.SZ | 紫光国微 |
| semiconductor | 688012.SH | 中微公司 |
| semiconductor | 603986.SH | 兆易创新 |
| semiconductor | 688716.SH | 瑞芯微 |
| pcb | 002463.SZ | 沪电股份 |
| pcb | 002916.SZ | 深南电路 |
| pcb | 600183.SH | 生益科技 |
| pcb | 002384.SZ | 东山精密 |
| power | 600900.SH | 长江电力 |
| power | 601985.SH | 中国核电 |
| power | 600025.SH | 华能水电 |
| power | 600905.SH | 三峡能源 |
| power_grid | 601669.SH | 中国电建 |
| power_grid | 600875.SH | 东方电气 |
| power_grid | 601727.SH | 上海电气 |
| power_grid | 601877.SH | 正泰电器 |

---

## 3. 文件布局

### 3.1 新增文件

```
quant/config/universes/default.txt
    → 28 只精选标的，格式与现有 universe 文件一致（# 注释 + 代码每行一个）

quant/config/universes/industry_map.json
    → {symbol: industry} 映射，覆盖 default.txt 全部标的

quant/src/domain/universe/__init__.py（空）
quant/src/domain/universe/universe_loader.py
    → load_universe(name: str) -> list[str]
    → load_industry_map() -> dict[str, str]

quant/tests/unit/universe/__init__.py（空）
quant/tests/unit/universe/test_universe_loader.py
    → 4 个单元测试
```

### 3.2 修改文件

```
quant/src/application/daily_run_service.py
    → symbols = load_universe("default")
    → 入口加交易日历守卫（非交易日返回 skipped）

quant/src/application/portfolio/optimizer_service.py
    → 删除 _INDUSTRY_MAP，改用 load_industry_map()

quant/src/application/risk/risk_gate_service.py
    → 删除 _INDUSTRY_MAP，改用 load_industry_map()

quant/src/application/signal/signal_engineering_service.py
    → 删除 _INDUSTRY_MAP，改用 load_industry_map()

quant/tests/contract/test_http_daily_endpoint.py
    → 补 1 个 case：非交易日返回 data.skipped=true

quant/tests/architecture/test_layering_rules.py
    → 补 domain.universe 白名单（允许 application/* import）
```

### 3.3 不改动文件

- `quant/config/universes/csi300.txt` / `follow.txt` / `self_select.txt`
- `quant/src/domain/market_data/sse_calendar.py`（已有，直接 import）
- CLI / HTTP schema / Rust 代码（标的池变化对外接口透明）

---

## 4. `universe_loader.py` 接口

```python
# quant/src/domain/universe/universe_loader.py

def load_universe(name: str) -> list[str]:
    """读取 quant/config/universes/<name>.txt，返回标的代码列表。
    跳过空行和 # 注释行。文件不存在时抛 FileNotFoundError。
    """

def load_industry_map() -> dict[str, str]:
    """读取 quant/config/universes/industry_map.json。
    返回 {symbol: industry_name} dict。
    """
```

**路径定位**：通过 `pathlib.Path(__file__).resolve().parents[N]` 定位到 `quant/config/universes/`，不依赖 CWD，测试友好。

**调用方式**：三个服务文件在模块级调用 `load_industry_map()`，结果赋给模块级变量（替换原有 `_INDUSTRY_MAP = {...}`），行为与现有完全一致。

---

## 5. 交易日历守卫

```python
# daily_run_service.py 入口

from domain.market_data.sse_calendar import is_sse_trading_day

def run_daily(as_of, root, bar_store=None, score_version=..., top_n=5):
    run_id = f"run_{as_of.replace('-', '')}_{str(uuid4())[:8]}"

    if not is_sse_trading_day(as_of):
        return ok_output(
            command="hf pipeline daily",
            run_id=run_id,
            data={"as_of": as_of, "skipped": True, "skip_reason": "non_trading_day"},
        )

    # 原有逻辑不变...
```

- `status: "ok"`，`data.skipped: true`，`data.skip_reason: "non_trading_day"`
- 不产生任何 warnings / errors
- `data` 中无 `portfolio` / `risk_gate` 等字段（未计算）

---

## 6. 测试策略

### 6.1 新增：`test_universe_loader.py`（4 个单元测试）

| 测试名 | 验证内容 |
|--------|----------|
| `test_load_universe_returns_symbols` | `load_universe("default")` 返回非空列表，无注释行，无空字符串 |
| `test_load_universe_skips_comments_and_blank` | 含 `#` 和空行的临时 txt → 只返回有效代码 |
| `test_load_universe_raises_on_missing_file` | 不存在的 name → `FileNotFoundError` |
| `test_load_industry_map_returns_dict` | `load_industry_map()` 返回 dict，default.txt 全部标的均有映射 |

### 6.2 修改：`test_http_daily_endpoint.py`（补 1 个 case）

| 测试名 | 验证内容 |
|--------|----------|
| `test_daily_skips_non_trading_day` | `as_of="2026-04-05"`（周日）→ `data.skipped=true`, `data.skip_reason="non_trading_day"` |

### 6.3 无需新增测试的部分

- 三处 `_INDUSTRY_MAP` 迁移属于纯重构，行为不变，现有测试已覆盖
- `load_industry_map()` 模块级调用方式与原硬编码等价

---

## 7. 架构约束

`domain/universe/` 属于 domain 层，可被 `application/*` 各层 import。需在 `test_layering_rules.py` 补充白名单，确保架构测试不误报。

依赖方向：
```
application/daily_run_service
application/portfolio/optimizer_service       →  domain/universe/universe_loader
application/risk/risk_gate_service
application/signal/signal_engineering_service

application/daily_run_service  →  domain/market_data/sse_calendar（已有）
```

无新外部依赖。
