use std::collections::BTreeMap;

use serde_json::Value;

fn supports_unicode() -> bool {
    let lang = std::env::var("LANG").unwrap_or_default().to_uppercase();
    lang.contains("UTF-8")
}

pub fn render_sync_runs_chart(payload: &Value) -> Result<String, String> {
    if !supports_unicode() {
        return Err("terminal does not support unicode chart characters".to_string());
    }

    let mut by_date: BTreeMap<String, (i64, i64, i64)> = BTreeMap::new();
    if let Some(items) = payload.get("items").and_then(Value::as_array) {
        for item in items {
            let date = item
                .get("date")
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            let status = item.get("status").and_then(Value::as_str).unwrap_or("");
            let symbols_count = item.get("symbols_count").and_then(Value::as_i64).unwrap_or(0);
            let entry = by_date.entry(date).or_insert((0, 0, 0));
            if status == "success" {
                entry.0 += 1;
            } else if status == "failed" {
                entry.1 += 1;
            }
            entry.2 += symbols_count;
        }
    }

    let mut out = String::new();
    out.push_str("Sync Trend (success/failed)\n");
    for (date, (success, failed, _)) in &by_date {
        let success_bar = "█".repeat((*success).clamp(0, 20) as usize);
        let failed_bar = "░".repeat((*failed).clamp(0, 20) as usize);
        out.push_str(&format!(
            "{date} S:{success} F:{failed} {success_bar}{failed_bar}\n"
        ));
    }

    out.push_str("\nSymbols Count Trend\n");
    for (date, (_, _, symbols_sum)) in &by_date {
        let bar = "█".repeat((*symbols_sum).clamp(0, 40) as usize);
        out.push_str(&format!("{date} {symbols_sum} {bar}\n"));
    }

    Ok(out)
}

