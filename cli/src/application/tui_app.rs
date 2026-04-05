//! Full-screen `hf tui`：先拉 instruments 全列表；选中标的 + 基准一次 `POST /v1/market-data/bars-bundle`（多周期），换标防抖后重拉；换周期用内存缓存。
//! 命中标的缓存时先画缓存，并在后台再拉同一 bundle，静默合并（stale-while-revalidate）。
//! 全屏会话已打开时，即使该标的尚无缓存，也只用空图 + 后台 POST，不再弹全屏「加载数据」遮罩。

use std::collections::{HashMap, VecDeque};
use std::io::{self, IsTerminal};
use std::sync::mpsc;
use std::thread;

use chrono::{Duration as ChronoDuration, Local};

use crate::application::tui_bars_bundle_cache::TuiBarsBundleCache;
use crate::application::bars_tui_aggregate::aggregate_market_bars_payload_for_tui;
use crate::application::services::market_data::fetch_universe_instruments_via_api;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_market_data_bars_bundle;
use crate::infrastructure::tui_renderer::{
    run_sync_runs_tui_iteration, sync_runs_tui_enter, sync_runs_tui_leave, SyncRunsTuiClose,
};
use serde_json::{json, Value};

const DEFAULT_BENCHMARK: &str = "000300.SH";
const TUI_MAX_DISPLAY_POINTS: usize = 2000;
const TUI_DEFAULT_UNIVERSE: &str = "csi300";
const TUI_DEFAULT_TIMEFRAME: &str = "1m";
const TUI_DEFAULT_QUERY_DAYS: i32 = 7;
const TUI_BUNDLE_LIMIT_PER_TF: i32 = 5000;
/// CSI300 量级下避免频繁换标时 LRU 挤掉已拉过的标的（此前 cap=32 会导致「回过头的股票」反复全屏拉数）。
const TUI_BUNDLE_CACHE_CAP: usize = 512;

fn touch_bundle_lru(order: &mut VecDeque<String>, key: &str) {
    order.retain(|k| k != key);
    order.push_back(key.to_string());
}

/// 与 instruments 列表对齐代码格式，避免 UI 回传的 symbol 与缓存 key 细微不一致导致每次都 miss。
fn normalize_preferred_against_universe(symbols: &[String], preferred: &mut String) {
    *preferred = preferred.trim().to_string();
    let cur = preferred.as_str();
    if let Some(canon) = symbols.iter().find(|s| s.as_str() == cur) {
        *preferred = canon.clone();
        return;
    }
    if let Some(found) = symbols.iter().find(|s| s.eq_ignore_ascii_case(cur)) {
        *preferred = found.clone();
    }
}

fn insert_bundle_cache_entry(
    map: &mut HashMap<String, TuiBarsBundleCache>,
    order: &mut VecDeque<String>,
    key: String,
    val: TuiBarsBundleCache,
) {
    map.insert(key.clone(), val);
    touch_bundle_lru(order, &key);
    while map.len() > TUI_BUNDLE_CACHE_CAP {
        let Some(oldest) = order.pop_front() else {
            break;
        };
        map.remove(&oldest);
    }
}

/// 从 bundle 缓存取出当前 timeframe 的 items，注入中文简称并做 TUI 聚合。
fn build_tui_display_payload(
    cache: &TuiBarsBundleCache,
    timeframe: &str,
    zh_by_symbol: &std::collections::HashMap<&str, &str>,
) -> (Value, bool) {
    if let Some(p) = cache.get_memoized_tui_payload(timeframe) {
        return (p, false);
    }

    let mut items: Vec<Value> = cache
        .raw_payload_for_timeframe(timeframe)
        .get("items")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();

    for it in &mut items {
        let Some(sym) = it.get("symbol").and_then(Value::as_str) else {
            continue;
        };
        let zh = zh_by_symbol
            .get(sym)
            .copied()
            .or_else(|| {
                zh_by_symbol
                    .iter()
                    .find(|(k, _)| k.eq_ignore_ascii_case(sym))
                    .map(|(_, v)| *v)
            })
            .filter(|z| !z.is_empty());
        let Some(zh) = zh else {
            continue;
        };
        if let Some(m) = it.as_object_mut() {
            m.insert("symbol_name_zh".to_string(), json!(zh));
        }
    }

    let raw_payload = json!({ "items": items });
    let (pl, agg) = aggregate_market_bars_payload_for_tui(&raw_payload, TUI_MAX_DISPLAY_POINTS);
    cache.set_memoized_tui_payload(timeframe, pl.clone());
    (pl, agg)
}

struct BgTuiRefreshMsg {
    symbol: String,
    timeframe: String,
    cache: TuiBarsBundleCache,
    tui_payload: Value,
}

struct BgTuiPoll<'a> {
    rx: &'a mpsc::Receiver<BgTuiRefreshMsg>,
    bundle_caches: &'a mut HashMap<String, TuiBarsBundleCache>,
    bundle_cache_lru: &'a mut VecDeque<String>,
    preferred: &'a str,
    timeframe: &'a str,
}

impl BgTuiPoll<'_> {
    fn drain_for_display(&mut self) -> Option<Value> {
        let mut latest_display = None;
        while let Ok(msg) = self.rx.try_recv() {
            let skip_empty_over_nonempty = self
                .bundle_caches
                .get(&msg.symbol)
                .is_some_and(|existing| {
                    let old_n = existing.item_count_for_timeframe(self.timeframe);
                    let new_n = msg.cache.item_count_for_timeframe(self.timeframe);
                    old_n > 0 && new_n == 0
                });
            if skip_empty_over_nonempty {
                continue;
            }
            insert_bundle_cache_entry(
                self.bundle_caches,
                self.bundle_cache_lru,
                msg.symbol.clone(),
                msg.cache,
            );
            if msg.symbol == self.preferred && msg.timeframe == self.timeframe {
                latest_display = Some(msg.tui_payload);
            }
        }
        latest_display
    }
}

/// 颗粒度阶梯（**细→粗**）：分时(1m)→日K→周K→月K→年K；TUI 内数字键 `1`–`5` 直选对应档（与 quant `aggregate_storage_rows` 一致）。
const TUI_TIMEFRAMES: &[&str] = &["1m", "1d", "1w", "1M", "1y"];

fn tui_date_window() -> (String, String) {
    let end = Local::now().date_naive();
    let start = end
        - ChronoDuration::days(i64::from(TUI_DEFAULT_QUERY_DAYS).saturating_sub(1).max(0));
    (
        start.format("%Y-%m-%d").to_string(),
        end.format("%Y-%m-%d").to_string(),
    )
}

pub fn run_tui_shell() -> Result<(), AppError> {
    if !io::stdout().is_terminal() {
        return Err(AppError::InvalidArgs(
            "hf tui 需要交互式终端（TTY）".to_string(),
        ));
    }

    let cfg = load_default_config()?;
    let timeout_ms = cfg.timeout_ms;

    let instruments_rows =
        fetch_universe_instruments_via_api(&cfg.server_url, TUI_DEFAULT_UNIVERSE, timeout_ms)?;
    if instruments_rows.is_empty() {
        return Err(AppError::InvalidArgs(format!(
            "no instruments returned for universe={TUI_DEFAULT_UNIVERSE} (check quant /v1/market-data/instruments)"
        )));
    }

    let symbols: Vec<String> = instruments_rows.iter().map(|(s, _)| s.clone()).collect();
    let mut preferred = symbols.first().expect("non-empty").clone();
    let mut timeframe = TUI_DEFAULT_TIMEFRAME.to_string();

    let zh_by_symbol: std::collections::HashMap<&str, &str> = instruments_rows
        .iter()
        .map(|(s, z)| (s.as_str(), z.as_str()))
        .collect();

    let mut terminal = None;
    let mut bundle_caches: HashMap<String, TuiBarsBundleCache> = HashMap::new();
    let mut bundle_cache_lru: VecDeque<String> = VecDeque::new();
    let (tx, rx) = mpsc::channel::<BgTuiRefreshMsg>();

    loop {
        normalize_preferred_against_universe(&symbols, &mut preferred);

        let (start_d, end_d) = tui_date_window();
        let need_fetch = !bundle_caches.contains_key(&preferred);

        if !need_fetch {
            touch_bundle_lru(&mut bundle_cache_lru, preferred.as_str());
        }

        let mut did_blocking_fetch = false;
        if need_fetch && terminal.is_none() {
            let bundle_syms = vec![preferred.clone(), DEFAULT_BENCHMARK.to_string()];
            let body = post_market_data_bars_bundle(
                &cfg.server_url,
                &bundle_syms,
                TUI_TIMEFRAMES,
                Some(&start_d),
                Some(&end_d),
                TUI_BUNDLE_LIMIT_PER_TF,
                timeout_ms,
            )?;
            let cache = TuiBarsBundleCache::from_bundle_response(&body)?;
            insert_bundle_cache_entry(
                &mut bundle_caches,
                &mut bundle_cache_lru,
                preferred.clone(),
                cache,
            );
            did_blocking_fetch = true;
        }

        let (tui_payload, aggregated) =
            if let Some(cache) = bundle_caches.get(&preferred) {
                build_tui_display_payload(cache, &timeframe, &zh_by_symbol)
            } else {
                aggregate_market_bars_payload_for_tui(&json!({ "items": [] }), TUI_MAX_DISPLAY_POINTS)
            };
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

        if !did_blocking_fetch {
            let tx_bg = tx.clone();
            let server_url = cfg.server_url.clone();
            let timeout_bg = timeout_ms;
            let sym_bg = preferred.clone();
            let tf_bg = timeframe.clone();
            let start_bg = start_d.clone();
            let end_bg = end_d.clone();
            let zh_rows = instruments_rows.clone();
            thread::spawn(move || {
                let bundle_syms = vec![sym_bg.clone(), DEFAULT_BENCHMARK.to_string()];
                let Ok(body) = post_market_data_bars_bundle(
                    &server_url,
                    &bundle_syms,
                    TUI_TIMEFRAMES,
                    Some(start_bg.as_str()),
                    Some(end_bg.as_str()),
                    TUI_BUNDLE_LIMIT_PER_TF,
                    timeout_bg,
                ) else {
                    return;
                };
                let Ok(cached) = TuiBarsBundleCache::from_bundle_response(&body) else {
                    return;
                };
                let zh_hm: std::collections::HashMap<&str, &str> = zh_rows
                    .iter()
                    .map(|(a, b)| (a.as_str(), b.as_str()))
                    .collect();
                let (pl, _) = build_tui_display_payload(&cached, tf_bg.as_str(), &zh_hm);
                let _ = tx_bg.send(BgTuiRefreshMsg {
                    symbol: sym_bg,
                    timeframe: tf_bg,
                    cache: cached,
                    tui_payload: pl,
                });
            });
        }
        let awaiting_initial_bars = !bundle_caches.contains_key(&preferred);
        let mut bg_poll = BgTuiPoll {
            rx: &rx,
            bundle_caches: &mut bundle_caches,
            bundle_cache_lru: &mut bundle_cache_lru,
            preferred: preferred.as_str(),
            timeframe: timeframe.as_str(),
        };
        let close = run_sync_runs_tui_iteration(
            term,
            &tui_payload,
            Some(instruments_rows.as_slice()),
            Some(preferred.as_str()),
            Some(DEFAULT_BENCHMARK),
            Some((TUI_TIMEFRAMES, timeframe.as_str())),
            Some(preferred.as_str()),
            awaiting_initial_bars,
            || bg_poll.drain_for_display(),
        );

        match close {
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
            Ok(SyncRunsTuiClose::SymbolChanged { symbol }) => {
                if symbols.iter().any(|s| s == symbol.as_str()) {
                    preferred = symbol;
                }
                continue;
            }
            Ok(SyncRunsTuiClose::RefreshRequested) => {
                bundle_caches.remove(&preferred);
                bundle_cache_lru.retain(|k| k != &preferred);
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
