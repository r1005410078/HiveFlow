use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_execution_plan;
use hf_cli::infrastructure::table_renderer::render_execution_plan_table;
use mockito::Server;
use serde_json::json;

#[test]
fn post_execution_plan_json_round_trip() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf execution plan","run_id":"exec_1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"as_of":"2026-04-01","slippage_bp":5,"estimated_total_cost_bp":7.1,"orders":[{"symbol":"600519.SH","direction":"buy","action":"open_long","quantity":100,"target_notional":120000.0,"current_notional":0.0,"close_price":1000.0,"limit_price":1000.5,"order_type":"limit","validity":"day","impact_bp":2.0}]},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock("POST", "/api/v1/execution/plan")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(body)
        .create();

    let out = post_execution_plan(
        &server.url(),
        "2026-04-01",
        json!({"600519.SH": 1.0}),
        Some(json!({"orders": []})),
        1_000_000.0,
        3000,
    )
    .expect("http");
    assert_eq!(out["command"], "hf execution plan");
    assert_eq!(out["data"]["orders"][0]["symbol"], "600519.SH");
}

#[test]
fn execution_plan_table_contains_buy_and_metrics() {
    let payload: serde_json::Value = serde_json::from_str(
        r#"{"schema_version":"1.0.0","command":"hf execution plan","status":"ok","data":{"as_of":"2026-04-01","slippage_bp":5,"estimated_total_cost_bp":6.4,"orders":[{"symbol":"600519.SH","direction":"buy","action":"open_long","quantity":100,"target_notional":120000.0,"current_notional":0.0,"close_price":1180.0,"limit_price":1180.59,"order_type":"limit","validity":"day","impact_bp":2.1}]},"warnings":[],"errors":[]}"#,
    )
    .unwrap();
    let table = render_execution_plan_table(&payload);
    assert!(table.contains("as_of: 2026-04-01"));
    assert!(table.contains("BUY"));
    assert!(table.contains("600519.SH"));
    assert!(table.contains("open_long"));
}

#[test]
fn post_execution_plan_returns_upstream_error_on_server_failure() {
    let mut server = Server::new();
    let _m = server
        .mock("POST", "/api/v1/execution/plan")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let err = post_execution_plan(
        &server.url(),
        "2026-04-01",
        json!({"600519.SH": 1.0}),
        Some(json!({"orders": []})),
        1_000_000.0,
        3000,
    )
    .expect_err("should fail on 502");

    match err {
        AppError::Upstream(status, body) => {
            assert_eq!(status, 502);
            assert_eq!(body["raw_body"], "bad gateway");
        }
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
