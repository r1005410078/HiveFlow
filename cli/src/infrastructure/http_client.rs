use reqwest::blocking::Client;
use serde_json::{json, Value};

use crate::error::AppError;
use crate::infrastructure::stdout_parser::parse_json;

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
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}

pub fn post_pipeline_compare(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    top_n: usize,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/pipeline/compare",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({
            "start_date": start_date,
            "end_date": end_date,
            "top_n": top_n,
        }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}

pub fn post_factor_optimize(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    factor_names: &[String],
    correlation_threshold: Option<f64>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/factor-optimization/evaluate",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let mut body = json!({
        "start_date": start_date,
        "end_date": end_date,
        "factor_names": factor_names,
        "constraints": {},
    });
    if let Some(threshold) = correlation_threshold {
        body["correlation_threshold"] = json!(threshold);
    }

    let response = client
        .post(url)
        .json(&body)
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
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
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_data_universe_sync(
    server_url: &str,
    universe: &str,
    provider: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/universes/sync",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({
            "universe": universe,
            "provider": provider,
        }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_symbol_names_sync(
    server_url: &str,
    universes: &[String],
    provider: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/universes/symbol-names/sync",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let body = if universes.is_empty() {
        json!({ "provider": provider })
    } else {
        json!({ "provider": provider, "universes": universes })
    };

    let response = client
        .post(url)
        .json(&body)
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn get_market_data_sync_runs(
    server_url: &str,
    days: i32,
    timeframe: Option<&str>,
    status: Option<&str>,
    request_id: Option<&str>,
    limit: Option<i32>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/sync-runs",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let mut request = client.get(url).query(&[("days", days.to_string())]);
    if let Some(tf) = timeframe {
        request = request.query(&[("timeframe", tf)]);
    }
    if let Some(st) = status {
        request = request.query(&[("status", st)]);
    }
    if let Some(req_id) = request_id {
        request = request.query(&[("request_id", req_id)]);
    }
    if let Some(lim) = limit {
        request = request.query(&[("limit", lim.to_string())]);
    }

    let response = request.send().map_err(AppError::HttpClient)?;
    let status_code = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status_code.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status_code.as_u16(), body));
    }
    parse_json(&body_text)
}

/// Optional query parameters for `GET /v1/market-data/bars` (session / cursor pagination).
#[derive(Clone, Copy, Default)]
pub struct BarsQueryOptions<'a> {
    pub session_date: Option<&'a str>,
    pub cursor_bar_time: Option<&'a str>,
    pub cursor_symbol: Option<&'a str>,
}

pub fn get_market_data_bars(
    server_url: &str,
    symbols: Option<&[String]>,
    timeframe: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    limit: Option<i32>,
    timeout_ms: u64,
    opts: BarsQueryOptions<'_>,
) -> Result<Value, AppError> {
    let url = format!("{}/v1/market-data/bars", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let mut request = client.get(url);
    if let Some(tf) = timeframe {
        request = request.query(&[("timeframe", tf)]);
    }
    if let Some(start) = start_date {
        request = request.query(&[("start_date", start)]);
    }
    if let Some(end) = end_date {
        request = request.query(&[("end_date", end)]);
    }
    if let Some(lim) = limit {
        request = request.query(&[("limit", lim.to_string())]);
    }
    if let Some(sd) = opts.session_date {
        request = request.query(&[("session_date", sd)]);
    }
    if let Some(cbt) = opts.cursor_bar_time {
        request = request.query(&[("cursor_bar_time", cbt)]);
    }
    if let Some(cs) = opts.cursor_symbol {
        request = request.query(&[("cursor_symbol", cs)]);
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
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status_code.as_u16(), body));
    }
    parse_json(&body_text)
}

/// `GET /v1/market-data/instruments` — universe file listing or DB symbol discovery.
pub fn get_market_data_instruments(
    server_url: &str,
    mode: &str,
    universe: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
    min_bars: Option<i32>,
    storage_timeframe: Option<&str>,
    limit: Option<i32>,
    cursor_symbol: Option<&str>,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/instruments",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let mut request = client.get(url).query(&[("mode", mode)]);
    if let Some(u) = universe {
        request = request.query(&[("universe", u)]);
    }
    if let Some(s) = start_date {
        request = request.query(&[("start_date", s)]);
    }
    if let Some(e) = end_date {
        request = request.query(&[("end_date", e)]);
    }
    if let Some(m) = min_bars {
        request = request.query(&[("min_bars", m.to_string())]);
    }
    if let Some(stf) = storage_timeframe {
        request = request.query(&[("storage_timeframe", stf)]);
    }
    if let Some(lim) = limit {
        request = request.query(&[("limit", lim.to_string())]);
    }
    if let Some(c) = cursor_symbol {
        request = request.query(&[("cursor_symbol", c)]);
    }

    let response = request.send().map_err(AppError::HttpClient)?;
    let status_code = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status_code.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status_code.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_signal_snapshot(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/signal/snapshot", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({"as_of": as_of}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}

pub fn get_sync_run_detail(
    server_url: &str,
    run_id: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/sync-runs/{}",
        server_url.trim_end_matches('/'),
        run_id
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client.get(url).send().map_err(AppError::HttpClient)?;
    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_sync_run_cancel(
    server_url: &str,
    run_id: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/sync-runs/{}/cancel",
        server_url.trim_end_matches('/'),
        run_id
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_sync_run_retry_failed(
    server_url: &str,
    run_id: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/v1/market-data/sync-runs/{}/retry-failed",
        server_url.trim_end_matches('/'),
        run_id
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({}))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }
    parse_json(&body_text)
}

pub fn post_signal_evaluate(
    server_url: &str,
    start_date: &str,
    end_date: &str,
    forward_days: u32,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!("{}/api/v1/signal/evaluate", server_url.trim_end_matches('/'));
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({
            "start_date": start_date,
            "end_date": end_date,
            "forward_days": forward_days,
        }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}

pub fn post_portfolio_optimize(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/portfolio/optimize",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({ "as_of": as_of }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}

pub fn post_risk_check(
    server_url: &str,
    as_of: &str,
    timeout_ms: u64,
) -> Result<Value, AppError> {
    let url = format!(
        "{}/api/v1/risk/check",
        server_url.trim_end_matches('/')
    );
    let client = build_client(server_url, timeout_ms)?;

    let response = client
        .post(url)
        .json(&json!({ "as_of": as_of, "target_weights": {} }))
        .send()
        .map_err(AppError::HttpClient)?;

    let status = response.status();
    let body_text = response.text().map_err(AppError::HttpClient)?;
    if !status.is_success() {
        let body =
            serde_json::from_str(&body_text).unwrap_or_else(|_| json!({ "raw_body": body_text }));
        return Err(AppError::Upstream(status.as_u16(), body));
    }

    parse_json(&body_text)
}
