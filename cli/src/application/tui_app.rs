//! Full-screen `hf tui`：先拉 instruments 全列表，再按批次拉全 universe 的 K 线（左侧列表与合并前一致）。

use std::io::{self, IsTerminal};

use chrono::{Duration as ChronoDuration, Local};

use crate::application::bars_fetch::{fetch_bars_merged_items_with_options, BarsFetchOptions};
use crate::application::bars_tui_aggregate::aggregate_market_bars_payload_for_tui;
use crate::application::requests::DataBarsRequest;
use crate::application::services::market_data::fetch_universe_instruments_via_api;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::tui_renderer::{
    render_sync_runs_tui_with_timeframes, SyncRunsTuiClose,
};
use serde_json::{json, Value};

const DEFAULT_BENCHMARK: &str = "000300.SH";
const TUI_MAX_DISPLAY_POINTS: usize = 2000;
const TUI_DEFAULT_UNIVERSE: &str = "csi300";
const TUI_DEFAULT_TIMEFRAME: &str = "1m";
const TUI_DEFAULT_QUERY_DAYS: i32 = 7;

/// 颗粒度阶梯（**细→粗**）：分时(1m)→日K→周K→月K→年K；TUI 内 `+` 更细、`-` 更粗（与 quant `aggregate_storage_rows` 一致）。
const TUI_TIMEFRAMES: &[&str] = &["1m", "1d", "1w", "1M", "1y"];

fn demo_bars_request(preferred_symbol: &str, timeframe: &str) -> DataBarsRequest {
    let end = Local::now().date_naive();
    let start = end
        - ChronoDuration::days(i64::from(TUI_DEFAULT_QUERY_DAYS).saturating_sub(1).max(0));
    DataBarsRequest {
        symbols: Some(preferred_symbol.to_string()),
        universe: None,
        timeframe: timeframe.to_string(),
        start_date: Some(start.format("%Y-%m-%d").to_string()),
        end_date: Some(end.format("%Y-%m-%d").to_string()),
        output: "json".into(),
        verbose: false,
        no_benchmark: false,
        limit: None,
        max_display_points: TUI_MAX_DISPLAY_POINTS,
        timeout_ms: None,
    }
}

pub fn run_tui_shell() -> Result<(), AppError> {
    if !io::stdout().is_terminal() {
        return Err(AppError::InvalidArgs(
            "hf tui 需要交互式终端（TTY）".to_string(),
        ));
    }

    let cfg = load_default_config()?;
    let timeout_ms = cfg.timeout_ms;

    let instruments =
        fetch_universe_instruments_via_api(&cfg.server_url, TUI_DEFAULT_UNIVERSE, timeout_ms)?;
    if instruments.is_empty() {
        return Err(AppError::InvalidArgs(format!(
            "no instruments returned for universe={TUI_DEFAULT_UNIVERSE} (check quant /v1/market-data/instruments)"
        )));
    }

    let symbols: Vec<String> = instruments.iter().map(|(s, _)| s.clone()).collect();
    let preferred = symbols.first().expect("non-empty").clone();
    let mut timeframe = TUI_DEFAULT_TIMEFRAME.to_string();

    loop {
        let req = demo_bars_request(preferred.as_str(), timeframe.as_str());

        // 多标的分批请求（与 `hf data bars --universe` 一致）；不在此对全 universe 做单标的游标跟页。
        let mut items = fetch_bars_merged_items_with_options(
            &cfg.server_url,
            &symbols,
            Some(req.timeframe.as_str()),
            req.start_date.as_deref(),
            req.end_date.as_deref(),
            req.limit,
            timeout_ms,
            BarsFetchOptions::default(),
        )?;

        let zh_by_symbol: std::collections::HashMap<&str, &str> = instruments
            .iter()
            .map(|(s, z)| (s.as_str(), z.as_str()))
            .collect();
        for it in &mut items {
            let Some(sym) = it.get("symbol").and_then(Value::as_str) else {
                continue;
            };
            let Some(zh) = zh_by_symbol.get(sym).copied().filter(|z| !z.is_empty()) else {
                continue;
            };
            if let Some(m) = it.as_object_mut() {
                m.insert("symbol_name_zh".to_string(), json!(zh));
            }
        }

        let raw_payload = json!({ "items": items });
        let (tui_payload, aggregated) =
            aggregate_market_bars_payload_for_tui(&raw_payload, TUI_MAX_DISPLAY_POINTS);
        if aggregated {
            eprintln!(
                "note: TUI display aggregated OHLC buckets (max {} points per symbol)",
                TUI_MAX_DISPLAY_POINTS
            );
        }

        match render_sync_runs_tui_with_timeframes(
            &tui_payload,
            Some(preferred.as_str()),
            Some(DEFAULT_BENCHMARK),
            Some((TUI_TIMEFRAMES, timeframe.as_str())),
        ) {
            Ok(SyncRunsTuiClose::Quit) => return Ok(()),
            Ok(SyncRunsTuiClose::TimeframeChanged(next)) => {
                timeframe = next;
                continue;
            }
            Err(reason) => return Err(AppError::InvalidArgs(reason)),
        }
    }
}
