use comfy_table::presets::UTF8_FULL;
use comfy_table::{Cell, ContentArrangement, Table};
use serde_json::Value;

fn truncate_middle(s: &str, head: usize, tail: usize) -> String {
    if s.len() <= head + tail + 1 {
        return s.to_string();
    }
    format!("{}...{}", &s[..head], &s[s.len() - tail..])
}

fn as_str(v: Option<&Value>) -> String {
    v.and_then(Value::as_str).unwrap_or("").to_string()
}

fn as_i64(v: Option<&Value>) -> String {
    v.and_then(Value::as_i64)
        .map(|n| n.to_string())
        .unwrap_or_else(|| "".to_string())
}

fn as_f64(v: Option<&Value>) -> String {
    v.and_then(Value::as_f64)
        .map(|n| format!("{n:.4}"))
        .unwrap_or_else(|| "".to_string())
}

pub fn render_sync_runs_table(payload: &Value, verbose: bool) -> String {
    if let Some(first) = payload
        .get("items")
        .and_then(Value::as_array)
        .and_then(|items| items.first())
    {
        if first.get("bar_time").is_some() && first.get("close").is_some() {
            return render_market_data_table(payload, verbose);
        }
    }

    render_sync_runs_status_table(payload, verbose)
}

fn render_market_data_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("bar_time"),
            Cell::new("symbol"),
            Cell::new("timeframe"),
            Cell::new("close"),
        ]);

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let bar_time = as_str(item.get("bar_time"));
            let symbol = as_str(item.get("symbol"));
            let timeframe = as_str(item.get("timeframe"));
            let close = as_f64(item.get("close"));
            table.add_row(vec![bar_time, symbol, timeframe, close]);

            if verbose {
                let open = as_f64(item.get("open"));
                let high = as_f64(item.get("high"));
                let low = as_f64(item.get("low"));
                let volume = as_f64(item.get("volume"));
                let source = as_str(item.get("data_source"));
                table.add_row(vec![
                    "".to_string(),
                    format!("o/h/l={open}/{high}/{low}"),
                    format!("vol={volume}"),
                    format!("src={source}"),
                ]);
            }
        }
    }
    format!("Market Data\n{}\n", table)
}

fn render_sync_runs_status_table(payload: &Value, verbose: bool) -> String {
    let mut table = Table::new();
    table
        .load_preset(UTF8_FULL)
        .set_content_arrangement(ContentArrangement::Dynamic)
        .set_header(vec![
            Cell::new("date"),
            Cell::new("status"),
            Cell::new("timeframe"),
            Cell::new("symbols_count"),
            Cell::new("run_id"),
            Cell::new("manifest_id"),
        ]);

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let date = as_str(item.get("date"));
            let status = as_str(item.get("status"));
            let timeframe = as_str(item.get("timeframe"));
            let symbols_count = as_i64(item.get("symbols_count"));
            let run_id = truncate_middle(&as_str(item.get("run_id")), 8, 6);
            let manifest_id = truncate_middle(&as_str(item.get("manifest_id")), 8, 6);
            table.add_row(vec![date, status, timeframe, symbols_count, run_id, manifest_id]);

            if verbose {
                let error_code = as_str(item.get("error_code"));
                let error_message = as_str(item.get("error_message"));
                let started_at = as_str(item.get("started_at"));
                let finished_at = as_str(item.get("finished_at"));
                table.add_row(vec![
                    "".to_string(),
                    format!("error={error_code}"),
                    format!("msg={}", truncate_middle(&error_message, 12, 10)),
                    "".to_string(),
                    format!("started={started_at}"),
                    format!("finished={finished_at}"),
                ]);
            }
        }
    }
    format!("Sync Runs\n{}\n", table)
}
