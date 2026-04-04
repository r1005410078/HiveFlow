//! 将 bars `items` 按标的分桶后做 OHLC 聚合，仅用于 TUI 展示路径。

use std::collections::BTreeMap;

use serde_json::{json, Value};

use crate::domain::bars_aggregate::{aggregate_ohlc_time_order, OhlcPoint};

use super::bars_fetch::sort_items;

fn item_to_ohlc(item: &Value) -> Option<OhlcPoint> {
    let bar_time = item.get("bar_time")?.as_str()?.to_string();
    let close = item.get("close").and_then(Value::as_f64)?;
    let open = item.get("open").and_then(Value::as_f64).unwrap_or(close);
    let high = item.get("high").and_then(Value::as_f64).unwrap_or(close);
    let low = item.get("low").and_then(Value::as_f64).unwrap_or(close);
    Some(OhlcPoint {
        bar_time,
        open,
        high,
        low,
        close,
    })
}

/// `max_display_points == 0`：不聚合，返回 `payload` 克隆与 `false`。
/// 否则按标的独立聚合；若任一标的发生合并则第二个返回值为 `true`。
pub fn aggregate_market_bars_payload_for_tui(
    payload: &Value,
    max_display_points: usize,
) -> (Value, bool) {
    if max_display_points == 0 {
        return (payload.clone(), false);
    }
    let Some(items) = payload.get("items").and_then(Value::as_array) else {
        return (payload.clone(), false);
    };
    if items.is_empty() {
        return (payload.clone(), false);
    }

    let mut by_symbol: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for item in items {
        let symbol = item
            .get("symbol")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        if symbol.is_empty() {
            continue;
        }
        by_symbol.entry(symbol).or_default().push(item.clone());
    }

    let mut out_items: Vec<Value> = Vec::new();
    let mut any_aggregated = false;

    for (symbol, mut vs) in by_symbol {
        vs.sort_by(|a, b| {
            let ta = a.get("bar_time").and_then(Value::as_str).unwrap_or("");
            let tb = b.get("bar_time").and_then(Value::as_str).unwrap_or("");
            ta.cmp(tb)
        });
        let n = vs.len();
        if n <= max_display_points {
            out_items.extend(vs);
            continue;
        }
        any_aggregated = true;
        let mut pts: Vec<OhlcPoint> = Vec::with_capacity(n);
        for v in &vs {
            if let Some(p) = item_to_ohlc(v) {
                pts.push(p);
            }
        }
        if pts.is_empty() {
            out_items.extend(vs);
            continue;
        }
        let agg = aggregate_ohlc_time_order(&pts, max_display_points);
        for p in agg {
            out_items.push(json!({
                "symbol": symbol,
                "bar_time": p.bar_time,
                "open": p.open,
                "high": p.high,
                "low": p.low,
                "close": p.close,
            }));
        }
    }

    sort_items(&mut out_items);
    (json!({ "items": out_items }), any_aggregated)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn no_aggregation_under_cap_per_symbol() {
        let payload = json!({
            "items": [
                {"symbol":"A","bar_time":"t1","open":1.0,"high":2.0,"low":0.5,"close":1.5},
                {"symbol":"A","bar_time":"t2","open":1.5,"high":2.5,"low":1.0,"close":2.0}
            ]
        });
        let (out, agg) = aggregate_market_bars_payload_for_tui(&payload, 10);
        assert!(!agg);
        assert_eq!(out["items"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn aggregates_per_symbol() {
        let mut items = Vec::new();
        for i in 0..5 {
            items.push(json!({
                "symbol": "X",
                "bar_time": format!("2026-04-0{i}T00:00:00Z"),
                "open": i as f64,
                "high": (i as f64) + 1.0,
                "low": (i as f64) - 0.5,
                "close": (i as f64) + 0.5,
            }));
        }
        let payload = json!({ "items": items });
        let (out, agg) = aggregate_market_bars_payload_for_tui(&payload, 2);
        assert!(agg);
        let arr = out["items"].as_array().unwrap();
        assert_eq!(arr.len(), 2);
    }
}
