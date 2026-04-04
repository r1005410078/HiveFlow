//! 标的解析、分批拉取 bars、合并与排序（`data query` / `data bars` 共用）。

use std::collections::BTreeSet;

use serde_json::Value;

use crate::error::AppError;
use crate::infrastructure::http_client::{get_market_data_bars, BarsQueryOptions};
use crate::infrastructure::repo_root::hiveflow_repo_root;
use crate::infrastructure::universe_loader::load_universe_symbols;

pub const SYMBOL_BATCH: usize = 30;

/// Max HTTP round-trips when following `next_cursor_bar_time` for a single symbol.
const MAX_BAR_CURSOR_PAGES: usize = 10_000;

/// Extra bars query behavior (session/cursor + optional multi-page fetch for one symbol).
#[derive(Clone, Copy, Default)]
pub struct BarsFetchOptions<'a> {
    pub query: BarsQueryOptions<'a>,
    pub follow_cursor_pages: bool,
}

pub fn parse_csv_symbols(input: Option<&str>) -> Vec<String> {
    input
        .map(|raw| {
            raw.split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default()
}

pub fn resolve_bar_symbols(
    symbols_csv: Option<&str>,
    universe: Option<&str>,
) -> Result<Vec<String>, AppError> {
    let mut set: BTreeSet<String> = BTreeSet::new();
    for s in parse_csv_symbols(symbols_csv) {
        set.insert(s);
    }
    if let Some(name) = universe {
        let root = hiveflow_repo_root().ok_or_else(|| {
            AppError::InvalidArgs(
                "cannot locate repo root (set HIVEFLOW_ROOT or run from HiveFlow checkout)"
                    .to_string(),
            )
        })?;
        for s in load_universe_symbols(&root, name)? {
            set.insert(s);
        }
    }
    if set.is_empty() {
        return Err(AppError::InvalidArgs(
            "need at least one symbol: pass --symbols and/or --universe".to_string(),
        ));
    }
    Ok(set.into_iter().collect())
}

pub fn merge_items(into: &mut Vec<Value>, batch: &Value) {
    if let Some(arr) = batch.get("items").and_then(Value::as_array) {
        into.extend(arr.iter().cloned());
    }
}

pub fn sort_items(items: &mut [Value]) {
    items.sort_by(|a, b| {
        let ta = a.get("bar_time").and_then(Value::as_str).unwrap_or("");
        let tb = b.get("bar_time").and_then(Value::as_str).unwrap_or("");
        let sa = a.get("symbol").and_then(Value::as_str).unwrap_or("");
        let sb = b.get("symbol").and_then(Value::as_str).unwrap_or("");
        ta.cmp(tb).then_with(|| sa.cmp(sb))
    });
}

pub fn fetch_bars_merged_items_with_options(
    server_url: &str,
    symbols: &[String],
    timeframe: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    limit: Option<i32>,
    timeout_ms: u64,
    options: BarsFetchOptions<'_>,
) -> Result<Vec<Value>, AppError> {
    let mut merged: Vec<Value> = Vec::new();
    for chunk in symbols.chunks(SYMBOL_BATCH) {
        let batch: Vec<String> = chunk.to_vec();
        if options.follow_cursor_pages && batch.len() == 1 {
            let sym = batch[0].clone();
            let mut cursor_bt: Option<String> = options
                .query
                .cursor_bar_time
                .filter(|s| !s.is_empty())
                .map(String::from);
            let mut pages = 0usize;
            loop {
                pages += 1;
                if pages > MAX_BAR_CURSOR_PAGES {
                    return Err(AppError::InvalidArgs(format!(
                        "bars cursor pagination exceeded {MAX_BAR_CURSOR_PAGES} pages"
                    )));
                }
                let q = BarsQueryOptions {
                    session_date: options.query.session_date,
                    cursor_bar_time: cursor_bt.as_deref(),
                    cursor_symbol: Some(
                        options
                            .query
                            .cursor_symbol
                            .unwrap_or(sym.as_str()),
                    ),
                };
                let v = get_market_data_bars(
                    server_url,
                    Some(&batch),
                    timeframe,
                    start_date,
                    end_date,
                    limit,
                    timeout_ms,
                    q,
                )?;
                merge_items(&mut merged, &v);
                let has_more = v
                    .get("has_more")
                    .and_then(Value::as_bool)
                    .unwrap_or(false);
                let next = v
                    .get("next_cursor_bar_time")
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty());
                if !has_more || next.is_none() {
                    break;
                }
                cursor_bt = next.map(String::from);
            }
        } else {
            let q = if batch.len() == 1 {
                options.query
            } else {
                BarsQueryOptions {
                    session_date: options.query.session_date,
                    cursor_bar_time: None,
                    cursor_symbol: None,
                }
            };
            let v = get_market_data_bars(
                server_url,
                Some(&batch),
                timeframe,
                start_date,
                end_date,
                limit,
                timeout_ms,
                q,
            )?;
            merge_items(&mut merged, &v);
        }
    }
    sort_items(&mut merged);
    Ok(merged)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn merge_and_sort_items() {
        use serde_json::json;
        let mut merged = Vec::new();
        merge_items(
            &mut merged,
            &json!({"items":[{"symbol":"B","bar_time":"2026-04-02T00:00:00Z"}]}),
        );
        merge_items(
            &mut merged,
            &json!({"items":[{"symbol":"A","bar_time":"2026-04-01T00:00:00Z"}]}),
        );
        sort_items(&mut merged);
        assert_eq!(
            merged[0].get("symbol").and_then(|v| v.as_str()),
            Some("A")
        );
        assert_eq!(
            merged[1].get("symbol").and_then(|v| v.as_str()),
            Some("B")
        );
    }
}
