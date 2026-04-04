//! Full-screen `hf tui`：先拉取服务端标的列表，再拉单标的 K 线（单标的时跟随 bars 游标分页）。

use std::io::{self, IsTerminal};

use chrono::{Duration as ChronoDuration, Local};

use crate::application::bars_fetch::{fetch_bars_merged_items_with_options, BarsFetchOptions};
use crate::application::bars_tui_aggregate::aggregate_market_bars_payload_for_tui;
use crate::application::requests::DataBarsRequest;
use crate::application::services::market_data::fetch_universe_symbols_via_api;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::tui_renderer::render_sync_runs_tui;
use serde_json::json;

const DEFAULT_BENCHMARK: &str = "000300.SH";
const TUI_MAX_DISPLAY_POINTS: usize = 2000;
const TUI_DEFAULT_UNIVERSE: &str = "csi300";
const TUI_DEFAULT_TIMEFRAME: &str = "1m";
const TUI_DEFAULT_QUERY_DAYS: i32 = 7;

fn demo_bars_request(preferred_symbol: &str) -> DataBarsRequest {
    let end = Local::now().date_naive();
    let start = end
        - ChronoDuration::days(i64::from(TUI_DEFAULT_QUERY_DAYS).saturating_sub(1).max(0));
    DataBarsRequest {
        symbols: Some(preferred_symbol.to_string()),
        universe: None,
        timeframe: TUI_DEFAULT_TIMEFRAME.into(),
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

    let symbols = fetch_universe_symbols_via_api(&cfg.server_url, TUI_DEFAULT_UNIVERSE, timeout_ms)?;
    if symbols.is_empty() {
        return Err(AppError::InvalidArgs(format!(
            "no instruments returned for universe={TUI_DEFAULT_UNIVERSE} (check quant /v1/market-data/instruments)"
        )));
    }

    let preferred = symbols.first().expect("non-empty");
    let req = demo_bars_request(preferred.as_str());

    let items = fetch_bars_merged_items_with_options(
        &cfg.server_url,
        std::slice::from_ref(preferred),
        Some(req.timeframe.as_str()),
        req.start_date.as_deref(),
        req.end_date.as_deref(),
        req.limit,
        timeout_ms,
        BarsFetchOptions {
            follow_cursor_pages: true,
            ..Default::default()
        },
    )?;

    let raw_payload = json!({ "items": items });
    let (tui_payload, aggregated) =
        aggregate_market_bars_payload_for_tui(&raw_payload, TUI_MAX_DISPLAY_POINTS);
    if aggregated {
        eprintln!(
            "note: TUI display aggregated OHLC buckets (max {} points per symbol)",
            TUI_MAX_DISPLAY_POINTS
        );
    }

    render_sync_runs_tui(&tui_payload, Some(preferred.as_str()), Some(DEFAULT_BENCHMARK))
        .map_err(AppError::InvalidArgs)
}
