use chrono::{Duration, NaiveDate};
use serde_json::{json, Value};

use crate::application::requests::FactorReplayRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_factor_optimize;
use crate::infrastructure::table_renderer::render_factor_replay_table;

fn parse_date(label: &str, value: &str) -> Result<NaiveDate, AppError> {
    NaiveDate::parse_from_str(value, "%Y-%m-%d").map_err(|err| {
        AppError::InvalidArgs(format!(
            "{label} must be a valid date in YYYY-MM-DD format: {err}"
        ))
    })
}

fn extract_top1_factors(payload: &Value) -> Vec<String> {
    payload
        .get("data")
        .and_then(|data| data.get("top_combinations"))
        .and_then(|top| top.get("items"))
        .and_then(Value::as_array)
        .and_then(|items| items.first())
        .and_then(|item| item.get("factors"))
        .and_then(Value::as_array)
        .map(|factors| {
            factors
                .iter()
                .filter_map(Value::as_str)
                .map(ToString::to_string)
                .collect()
        })
        .unwrap_or_default()
}

pub fn run_replay(
    server_url: &str,
    timeout_ms: u64,
    args: &FactorReplayRequest,
) -> Result<Value, AppError> {
    if args.factor_names.is_empty() {
        return Err(AppError::InvalidArgs(
            "--factors must include at least one factor name".to_string(),
        ));
    }

    let start_date = parse_date("start_date", &args.start_date)?;
    let end_date = parse_date("end_date", &args.end_date)?;
    if start_date > end_date {
        return Err(AppError::InvalidArgs(
            "--start-date must be on or before --end-date".to_string(),
        ));
    }

    let mut daily_items = Vec::new();
    let mut error_days = 0_i64;
    let mut pass_days = 0_i64;
    let mut watch_days = 0_i64;
    let mut fail_days = 0_i64;
    let mut total_alert_count = 0_i64;
    let mut top1_change_days = 0_i64;
    let mut previous_success_top1: Option<Vec<String>> = None;

    let mut current = start_date;
    while current <= end_date {
        let as_of = current.format("%Y-%m-%d").to_string();
        match post_factor_optimize(
            server_url,
            &as_of,
            &as_of,
            &args.factor_names,
            args.correlation_threshold,
            timeout_ms,
        ) {
            Ok(payload) => {
                let release_gate_status = payload
                    .get("data")
                    .and_then(|data| data.get("release_gate"))
                    .and_then(|gate| gate.get("status"))
                    .and_then(Value::as_str)
                    .unwrap_or("unknown")
                    .to_string();
                let alert_count = payload
                    .get("data")
                    .and_then(|data| data.get("correlation_analysis"))
                    .and_then(|analysis| analysis.get("alert_count"))
                    .and_then(Value::as_i64)
                    .unwrap_or(0);
                let top1_factors = extract_top1_factors(&payload);

                total_alert_count += alert_count;
                match release_gate_status.as_str() {
                    "pass" => pass_days += 1,
                    "watch" => watch_days += 1,
                    "fail" => fail_days += 1,
                    _ => {}
                }

                if let Some(previous) = previous_success_top1.as_ref() {
                    if previous != &top1_factors {
                        top1_change_days += 1;
                    }
                }
                previous_success_top1 = Some(top1_factors.clone());

                daily_items.push(json!({
                    "as_of": as_of,
                    "fetch_status": "ok",
                    "release_gate_status": release_gate_status,
                    "alert_count": alert_count,
                    "top1_factors": top1_factors,
                }));
            }
            Err(err) => {
                error_days += 1;
                daily_items.push(json!({
                    "as_of": as_of,
                    "fetch_status": "error",
                    "release_gate_status": "unknown",
                    "alert_count": 0,
                    "top1_factors": [],
                    "error_message": err.to_string(),
                }));
            }
        }

        current += Duration::days(1);
    }

    let days = daily_items.len() as i64;
    let avg_alert_count = if days == 0 {
        0.0
    } else {
        total_alert_count as f64 / days as f64
    };

    Ok(json!({
        "summary": {
            "days": days,
            "error_days": error_days,
            "pass_days": pass_days,
            "watch_days": watch_days,
            "fail_days": fail_days,
            "avg_alert_count": avg_alert_count,
            "top1_change_days": top1_change_days,
        },
        "daily_items": daily_items,
    }))
}

pub fn handle(args: FactorReplayRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = run_replay(&cfg.server_url, cfg.timeout_ms, &args)?;

    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => print!("{}", render_factor_replay_table(&out)),
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for factor replay: {other} (expected: json|table)"
            )));
        }
    }

    Ok(())
}
