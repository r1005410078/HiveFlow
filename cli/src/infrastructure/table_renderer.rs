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

pub fn render_sync_runs_table(payload: &Value, verbose: bool) -> String {
    let mut out = String::new();
    out.push_str("date | status | timeframe | symbols_count | run_id | manifest_id\n");
    out.push_str("-----|--------|-----------|---------------|--------|------------\n");

    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let date = as_str(item.get("date"));
            let status = as_str(item.get("status"));
            let timeframe = as_str(item.get("timeframe"));
            let symbols_count = as_i64(item.get("symbols_count"));
            let run_id = truncate_middle(&as_str(item.get("run_id")), 8, 6);
            let manifest_id = truncate_middle(&as_str(item.get("manifest_id")), 8, 6);
            out.push_str(&format!(
                "{date} | {status} | {timeframe} | {symbols_count} | {run_id} | {manifest_id}\n"
            ));

            if verbose {
                let error_code = as_str(item.get("error_code"));
                let error_message = as_str(item.get("error_message"));
                let started_at = as_str(item.get("started_at"));
                let finished_at = as_str(item.get("finished_at"));
                out.push_str(&format!(
                    "  error_code={error_code}, error_message={error_message}, started_at={started_at}, finished_at={finished_at}\n"
                ));
            }
        }
    }
    out
}

