//! Full-screen `hf tui`：先拉 instruments 全列表，再按批次拉全 universe 的 K 线（左侧列表与合并前一致）。

use std::io::{self, IsTerminal};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use chrono::{Duration as ChronoDuration, Local};

use crate::application::bars_fetch::{
    fetch_bars_merged_items_with_options, BarsFetchOptions,
};
use crate::application::bars_tui_aggregate::aggregate_market_bars_payload_for_tui;
use crate::application::requests::DataBarsRequest;
use crate::application::services::market_data::fetch_universe_instruments_via_api;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::tui_renderer::{
    run_sync_runs_tui_iteration, sync_runs_tui_draw_loading, sync_runs_tui_enter,
    sync_runs_tui_leave, SyncRunsTuiClose, SyncRunsTuiTerminal,
};
use serde_json::{json, Value};

const DEFAULT_BENCHMARK: &str = "000300.SH";
const TUI_MAX_DISPLAY_POINTS: usize = 2000;
const TUI_DEFAULT_UNIVERSE: &str = "csi300";
const TUI_DEFAULT_TIMEFRAME: &str = "1m";
const TUI_DEFAULT_QUERY_DAYS: i32 = 7;

/// 颗粒度阶梯（**细→粗**）：分时(1m)→日K→周K→月K→年K；TUI 内数字键 `1`–`5` 直选对应档（与 quant `aggregate_storage_rows` 一致）。
const TUI_TIMEFRAMES: &[&str] = &["1m", "1d", "1w", "1M", "1y"];

fn timeframe_detail_for_loading(tf: &str) -> String {
    let zh = match tf {
        "1m" => "分时",
        "1d" => "日K",
        "1w" => "周K",
        "1M" => "月K",
        "1y" => "年K",
        _ => "",
    };
    if zh.is_empty() {
        tf.to_string()
    } else {
        format!("{zh} ({tf})")
    }
}

/// 在已有全屏 TUI 会话中拉 bars：后台 HTTP + 主线程刷加载动画，避免切换颗粒度时长时间无反馈。
fn fetch_bars_merged_with_loading_overlay(
    terminal: &mut SyncRunsTuiTerminal,
    server_url: &str,
    symbols: &[String],
    req: &DataBarsRequest,
    timeout_ms: u64,
) -> Result<Vec<Value>, AppError> {
    let server_url = server_url.to_string();
    let symbols = symbols.to_vec();
    let timeframe = req.timeframe.clone();
    let start_date = req.start_date.clone();
    let end_date = req.end_date.clone();
    let limit = req.limit;

    let (tx, rx) = mpsc::channel();
    thread::spawn(move || {
        let res = fetch_bars_merged_items_with_options(
            &server_url,
            &symbols,
            Some(timeframe.as_str()),
            start_date.as_deref(),
            end_date.as_deref(),
            limit,
            timeout_ms,
            BarsFetchOptions::default(),
        );
        let _ = tx.send(res);
    });

    let detail = timeframe_detail_for_loading(req.timeframe.as_str());
    let mut tick = 0usize;
    loop {
        sync_runs_tui_draw_loading(terminal, &detail, tick)
            .map_err(AppError::InvalidArgs)?;
        tick = tick.wrapping_add(1);
        match rx.recv_timeout(Duration::from_millis(80)) {
            Ok(Ok(items)) => return Ok(items),
            Ok(Err(e)) => return Err(e),
            Err(mpsc::RecvTimeoutError::Timeout) => continue,
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                return Err(AppError::InvalidArgs(
                    "bars 请求异常结束（线程断开）".to_string(),
                ));
            }
        }
    }
}

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
    let mut preferred = symbols.first().expect("non-empty").clone();
    let mut timeframe = TUI_DEFAULT_TIMEFRAME.to_string();

    let zh_by_symbol: std::collections::HashMap<&str, &str> = instruments
        .iter()
        .map(|(s, z)| (s.as_str(), z.as_str()))
        .collect();

    let mut terminal = None;

    loop {
        let req = demo_bars_request(preferred.as_str(), timeframe.as_str());

        // 多标的分批请求（与 `hf data bars --universe` 一致）；不在此对全 universe 做单标的游标跟页。
        let mut items = match terminal.as_mut() {
            Some(t) => match fetch_bars_merged_with_loading_overlay(
                t,
                &cfg.server_url,
                &symbols,
                &req,
                timeout_ms,
            ) {
                Ok(i) => i,
                Err(e) => {
                    if let Some(mut t) = terminal.take() {
                        sync_runs_tui_leave(&mut t);
                    }
                    return Err(e);
                }
            },
            None => match fetch_bars_merged_items_with_options(
                &cfg.server_url,
                &symbols,
                Some(req.timeframe.as_str()),
                req.start_date.as_deref(),
                req.end_date.as_deref(),
                req.limit,
                timeout_ms,
                BarsFetchOptions::default(),
            ) {
                Ok(i) => i,
                Err(e) => return Err(e),
            },
        };

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

        if terminal.is_none() {
            let t = match sync_runs_tui_enter() {
                Ok(t) => t,
                Err(reason) => return Err(AppError::InvalidArgs(reason)),
            };
            terminal = Some(t);
        }
        let term = terminal.as_mut().expect("terminal open");

        match run_sync_runs_tui_iteration(
            term,
            &tui_payload,
            Some(preferred.as_str()),
            Some(DEFAULT_BENCHMARK),
            Some((TUI_TIMEFRAMES, timeframe.as_str())),
        ) {
            Ok(SyncRunsTuiClose::Quit) => {
                if let Some(mut t) = terminal.take() {
                    sync_runs_tui_leave(&mut t);
                }
                return Ok(());
            }
            Ok(SyncRunsTuiClose::TimeframeChanged {
                timeframe: next_tf,
                selected_symbol,
            }) => {
                timeframe = next_tf;
                if symbols.iter().any(|s| s == selected_symbol.as_str()) {
                    preferred = selected_symbol;
                }
                continue;
            }
            Err(reason) => {
                if let Some(mut t) = terminal.take() {
                    sync_runs_tui_leave(&mut t);
                }
                return Err(AppError::InvalidArgs(reason));
            }
        }
    }
}
