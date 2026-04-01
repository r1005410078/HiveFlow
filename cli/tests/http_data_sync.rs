use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_data_sync;
use mockito::Server;

#[test]
fn data_sync_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/sync")
        .match_header("content-type", "application/json")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"status":"success","run_id":"run_001","timeframe":"1d","days":5,"effective_symbols_count":2,"manifest_ids":["mf_001"]}"#,
        )
        .create();

    let out = post_data_sync(&server.url(), 5, "2026-04-01", "1d", None, None, None, 1000)
        .expect("sync should succeed");

    assert_eq!(out["status"], "success");
    assert_eq!(out["timeframe"], "1d");
    assert_eq!(out["days"], 5);
}

#[test]
fn data_sync_returns_upstream_error() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/sync")
        .with_status(400)
        .with_header("content-type", "application/json")
        .with_body(r#"{"error":{"code":"INVALID_ARGUMENT","message":"bad days"}}"#)
        .create();

    let err = post_data_sync(&server.url(), 0, "2026-04-01", "1d", None, None, None, 1000)
        .expect_err("request should fail");

    match err {
        AppError::Upstream(status, _) => assert_eq!(status, 400),
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}

