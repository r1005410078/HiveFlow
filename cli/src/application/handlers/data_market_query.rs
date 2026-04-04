use chrono::{Duration, Local, NaiveDate};
use serde_json::json;

use crate::application::bars_fetch::{fetch_bars_merged_items, resolve_bar_symbols};
use crate::application::requests::DataMarketQueryRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::table_renderer::render_market_data_bars_table;
use crate::infrastructure::tui_renderer::render_market_data_bars_paged_table_tui;

fn resolve_date_window(args: &DataMarketQueryRequest) -> Result<(String, String), AppError> {
    let parse_d = |s: &str| {
        NaiveDate::parse_from_str(s, "%Y-%m-%d").map_err(|_| {
            AppError::InvalidArgs(format!("invalid date YYYY-MM-DD: {s}"))
        })
    };

    match (&args.start_date, &args.end_date) {
        (Some(s), Some(e)) => {
            let sd = parse_d(s)?;
            let ed = parse_d(e)?;
            if sd > ed {
                return Err(AppError::InvalidArgs(
                    "start_date must be on or before end_date".to_string(),
                ));
            }
            Ok((s.clone(), e.clone()))
        }
        (Some(_), None) => Err(AppError::InvalidArgs(
            "start_date requires end_date (or omit both and use --days with optional --end-date)"
                .to_string(),
        )),
        (None, Some(e)) => {
            let ed = parse_d(e)?;
            if args.days < 1 {
                return Err(AppError::InvalidArgs("--days must be >= 1".to_string()));
            }
            let sd = ed
                .checked_sub_signed(Duration::days(i64::from(args.days) - 1))
                .ok_or_else(|| AppError::InvalidArgs("date range underflow".to_string()))?;
            Ok((sd.format("%Y-%m-%d").to_string(), e.clone()))
        }
        (None, None) => {
            if args.days < 1 {
                return Err(AppError::InvalidArgs("--days must be >= 1".to_string()));
            }
            let ed = Local::now().date_naive();
            let sd = ed
                .checked_sub_signed(Duration::days(i64::from(args.days) - 1))
                .ok_or_else(|| AppError::InvalidArgs("date range underflow".to_string()))?;
            Ok((
                sd.format("%Y-%m-%d").to_string(),
                ed.format("%Y-%m-%d").to_string(),
            ))
        }
    }
}

pub fn handle(args: DataMarketQueryRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let (start_date, end_date) = resolve_date_window(&args)?;
    let symbols = resolve_bar_symbols(args.symbols.as_deref(), args.universe.as_deref())?;
    let per_request_limit = args.limit.unwrap_or(5000).min(10_000);

    let mut merged = fetch_bars_merged_items(
        &cfg.server_url,
        &symbols,
        Some(args.timeframe.as_str()),
        Some(start_date.as_str()),
        Some(end_date.as_str()),
        Some(per_request_limit),
        timeout_ms,
    )?;

    if let Some(lim) = args.limit {
        if merged.len() > lim as usize {
            merged.truncate(lim as usize);
        }
    }

    let payload = json!({ "items": merged });

    match args.output.as_str() {
        "json" => print!("{payload}"),
        "table" => {
            let table = render_market_data_bars_table(&payload, args.verbose);
            print!("{table}");
        }
        "tui" => match render_market_data_bars_paged_table_tui(&payload, args.verbose) {
            Ok(()) => {}
            Err(reason) => {
                eprintln!("warning: tui unavailable ({reason}), fallback to table");
                let table = render_market_data_bars_table(&payload, args.verbose);
                print!("{table}");
            }
        },
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for data query: {other} (expected: json|tui|table)"
            )));
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn req(
        days: i32,
        start_date: Option<&str>,
        end_date: Option<&str>,
    ) -> DataMarketQueryRequest {
        DataMarketQueryRequest {
            days,
            end_date: end_date.map(String::from),
            start_date: start_date.map(String::from),
            symbols: None,
            universe: None,
            timeframe: "1d".into(),
            limit: None,
            output: "json".into(),
            verbose: false,
            timeout_ms: None,
        }
    }

    #[test]
    fn resolve_window_start_without_end_errors() {
        let e = resolve_date_window(&req(5, Some("2026-04-01"), None)).unwrap_err();
        assert!(e.to_string().contains("end_date"));
    }

    #[test]
    fn resolve_window_start_after_end_errors() {
        let e = resolve_date_window(&req(
            5,
            Some("2026-04-02"),
            Some("2026-04-01"),
        ))
        .unwrap_err();
        assert!(e.to_string().contains("start_date"));
    }

    #[test]
    fn resolve_window_explicit_range() {
        let (s, e) = resolve_date_window(&req(
            99,
            Some("2026-04-01"),
            Some("2026-04-03"),
        ))
        .unwrap();
        assert_eq!(s, "2026-04-01");
        assert_eq!(e, "2026-04-03");
    }

    #[test]
    fn resolve_window_end_date_and_days() {
        let (s, e) = resolve_date_window(&req(3, None, Some("2026-04-05"))).unwrap();
        assert_eq!(e, "2026-04-05");
        assert_eq!(s, "2026-04-03");
    }

    #[test]
    fn merge_and_sort_items() {
        use crate::application::bars_fetch::{merge_items, sort_items};
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
