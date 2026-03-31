use reqwest::blocking::Client;
use serde_json::{json, Value};

use crate::error::AppError;

pub fn post_daily(server_url: &str, as_of: &str, timeout_ms: u64) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/pipeline/daily", server_url.trim_end_matches('/'));
    let client = Client::builder()
        .timeout(std::time::Duration::from_millis(timeout_ms))
        .build()
        .map_err(AppError::HttpClient)?;

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
