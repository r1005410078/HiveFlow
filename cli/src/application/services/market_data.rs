//! HTTP-backed instrument listing for `hf tui` (lazy list from quant, not local universe files).

use crate::error::AppError;
use crate::infrastructure::http_client::get_market_data_instruments;

const INSTRUMENTS_PAGE_LIMIT: i32 = 2000;
const MAX_INSTRUMENT_PAGES: usize = 500;

/// Paginate `GET /v1/market-data/instruments` until `has_more` is false.
pub fn fetch_universe_symbols_via_api(
    server_url: &str,
    universe: &str,
    timeout_ms: u64,
) -> Result<Vec<String>, AppError> {
    let mut all: Vec<String> = Vec::new();
    let mut cursor: Option<String> = None;
    let mut pages = 0usize;
    while pages < MAX_INSTRUMENT_PAGES {
        pages += 1;
        let v = get_market_data_instruments(
            server_url,
            "universe",
            Some(universe),
            None,
            None,
            None,
            None,
            Some(INSTRUMENTS_PAGE_LIMIT),
            cursor.as_deref(),
            timeout_ms,
        )?;
        if let Some(arr) = v.get("items").and_then(|x| x.as_array()) {
            for item in arr {
                if let Some(sym) = item.get("symbol").and_then(|x| x.as_str()) {
                    all.push(sym.to_string());
                }
            }
        }
        let has_more = v.get("has_more").and_then(|x| x.as_bool()).unwrap_or(false);
        if !has_more {
            break;
        }
        let next = v
            .get("next_cursor_symbol")
            .and_then(|x| x.as_str())
            .filter(|s| !s.is_empty())
            .map(String::from);
        let Some(n) = next else {
            break;
        };
        cursor = Some(n);
    }
    Ok(all)
}
