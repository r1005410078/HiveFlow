# 实现计划：bars-bundle + TUI 按需加载

**日期**：2026-04-05  
**关联 spec**：[2026-04-05-market-data-bars-bundle-design.md](../specs/2026-04-05-market-data-bars-bundle-design.md)

## 目标

1. Python：`BarsQueryService.query_bundle` + `POST /v1/market-data/bars-bundle` + 单元测试。
2. Rust：`post_market_data_bars_bundle`、`TuiBarsBundleCache`、`tui_app` 主循环（换标拉 bundle、换周期用缓存）。
3. TUI：`SymbolChanged` + 防抖；全市场列表 + 仅选中行展示最新价；基准曲线从 payload 单独取 series。
4. 验证：`make architecture-check`、`make check`；更新 `AGENTS.md` 7.6 接口摘要。

## 须改路径

- `quant/src/application/market_data/bars_query_service.py`
- `quant/src/interfaces/http/schemas_market_data.py`
- `quant/src/interfaces/http/routes_market_data.py`
- `quant/src/interfaces/http/dependencies.py`
- `quant/tests/unit/market_data/test_bars_bundle_query_service.py`（新建）
- `cli/src/infrastructure/http_client.rs`
- `cli/src/application/tui_bars_bundle_cache.rs`（新建）
- `cli/src/application/mod.rs`
- `cli/src/application/tui_app.rs`
- `cli/src/infrastructure/tui_renderer.rs`
- `cli/tests/architecture_rules.rs`（若新增 application 模块需声明）
- `AGENTS.md`

## 验证命令

```bash
make architecture-check
make check
```
