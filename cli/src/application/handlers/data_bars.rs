use serde_json::{json, Value};

use crate::application::bars_fetch::{
    fetch_bars_merged_items_with_options, resolve_bar_symbols, BarsFetchOptions,
};
use crate::application::bars_tui_aggregate::aggregate_market_bars_payload_for_tui;
use crate::application::requests::DataBarsRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::table_renderer::render_market_data_bars_table;
use crate::infrastructure::tui_renderer::render_sync_runs_tui;

const DEFAULT_BENCHMARK_SYMBOL: &str = "000300.SH";

fn warn_if_no_bars_rows(payload: &Value, timeframe: &str, server_url: &str, symbol_count: usize) {
    let n = payload
        .get("items")
        .and_then(Value::as_array)
        .map(|a| a.len())
        .unwrap_or(0);
    if n > 0 {
        return;
    }
    eprintln!(
        "warning: market-data bars API returned 0 rows ({} symbol(s) after --symbols/--universe merge).",
        symbol_count
    );
    eprintln!(
        "  Often the DB has data under a different timeframe than the query (e.g. sync used --timeframe 1m but this command uses 1d). Match --timeframe to the sync, or re-sync with 1d."
    );
    eprintln!(
        "  Also check date range, ~/.hiveflow/config.toml server_url points at the server using that DB, and try: hf data bars ... --output json"
    );
    eprintln!("  Current: server_url={server_url} timeframe={timeframe}");
}

pub fn handle(args: DataBarsRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let symbols = resolve_bar_symbols(args.symbols.as_deref(), args.universe.as_deref())?;
    let benchmark_symbol = if args.no_benchmark {
        None
    } else {
        Some(DEFAULT_BENCHMARK_SYMBOL)
    };

    let follow_cursor_pages = args.output == "tui" && symbols.len() == 1;
    let merged = fetch_bars_merged_items_with_options(
        &cfg.server_url,
        &symbols,
        Some(args.timeframe.as_str()),
        args.start_date.as_deref(),
        args.end_date.as_deref(),
        args.limit,
        timeout_ms,
        BarsFetchOptions {
            follow_cursor_pages,
            ..Default::default()
        },
    )?;

    let raw_payload = json!({ "items": merged });
    warn_if_no_bars_rows(
        &raw_payload,
        args.timeframe.as_str(),
        cfg.server_url.as_str(),
        symbols.len(),
    );

    match args.output.as_str() {
        "json" => print!("{raw_payload}"),
        "table" => {
            let table = render_market_data_bars_table(&raw_payload, args.verbose);
            print!("{table}");
        }
        "tui" => {
            let preferred_symbol = symbols.first().map(|s| s.as_str());
            let (tui_payload, aggregated) =
                aggregate_market_bars_payload_for_tui(&raw_payload, args.max_display_points);
            if aggregated {
                eprintln!(
                    "note: TUI display aggregated OHLC buckets (max {} points per symbol; see --max-display-points)",
                    args.max_display_points
                );
            }
            match render_sync_runs_tui(&tui_payload, preferred_symbol, benchmark_symbol) {
                Ok(()) => {}
                Err(reason) => {
                    eprintln!("warning: tui output unavailable ({reason}), fallback to table");
                    let table = render_market_data_bars_table(&tui_payload, args.verbose);
                    print!("{table}");
                }
            }
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for data bars: {other} (expected: json|table|tui)"
            )));
        }
    }

    Ok(())
}
