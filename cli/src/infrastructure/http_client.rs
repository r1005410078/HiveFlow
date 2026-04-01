use reqwest::blocking::Client;
use serde_json::{json, Value};

use crate::error::AppError;

fn build_client(server_url: &str, timeout_ms: u64) -> Result<Client, AppError> {
    let mut builder = Client::builder().timeout(std::time::Duration::from_millis(timeout_ms));
    let lower = server_url.to_ascii_lowercase();
    if lower.contains("127.0.0.1") || lower.contains("localhost") {
        // Local quant service should bypass system proxies to avoid accidental 502 from proxy gateways.
        builder = builder.no_proxy();
    }
    builder.build().map_err(AppError::HttpClient)
}

pub fn post_daily(server_url: &str, as_of: &str, timeout_ms: u64) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/pipeline/daily", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({"as_of": as_of}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body = serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    serde_json::from_str(&body_text).map_err(AppError::InvalidJson)
}

pub fn post_data_sync(
    server_url: &str,
    days: i32,
    end_date: &str,
    timeframe: &str,
    symbols: Option<&[String]>,
    universe: Option<&str>,
    request_id: Option<&str>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/v1/market-data/sync", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({
            "days": days,
            "end_date": end_date,
            "timeframe": timeframe,
            "symbols": symbols,
            "universe": universe,
            "request_id": request_id,
        }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body = serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    serde_json::from_str(&body_text).map_err(AppError::InvalidJson)
}

pub fn get_data_sync_runs(
    server_url: &str,
    days: i32,
    timeframe: Option<&str>,
    symbols: Option<&[String]>,
    status: Option<&str>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/v1/market-data/sync-runs", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let mut request = client.get(url).query(&[("days", days.to_string())]);
    if let Some(tf) = timeframe {
        request = request.query(&[("timeframe", tf)]);
    }
    if let Some(st) = status {
        request = request.query(&[("status", st)]);
    }
    if let Some(list) = symbols {
        for s in list {
            request = request.query(&[("symbols", s)]);
        }
    }

    let response = request.send().map_err(AppError::HttpClient)?;
    let status_code = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status_code.is_success() {
        let body = serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status_code.as_u16(), body));
    }
    serde_json::from_str(&body_text).map_err(AppError::InvalidJson)
}
