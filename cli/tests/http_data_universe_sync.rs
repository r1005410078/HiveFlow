use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_data_universe_sync;
use mockito::Server;

#[test]
fn data_universe_sync_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/universes/sync")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "universe": "csi300",
            "provider": "akshare",
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"universe":"csi300","provider":"akshare","symbols_count":300,"file_path":"/tmp/csi300.txt","updated_at":"2026-04-03T00:00:00+00:00"}"#,
        )
        .create();

    let out = post_data_universe_sync(&server.url(), "csi300", "akshare", 1000)
        .expect("universe sync should succeed");

    assert_eq!(out["universe"], "csi300");
    assert_eq!(out["provider"], "akshare");
    assert_eq!(out["symbols_count"], 300);
}

#[test]
fn data_universe_sync_returns_upstream_error() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/universes/sync")
        .with_status(503)
        .with_header("content-type", "application/json")
        .with_body(r#"{"detail":{"code":"UNIVERSE_SYNC_PROVIDER_ERROR","message":"provider unavailable"}}"#)
        .create();

    let err = post_data_universe_sync(&server.url(), "csi300", "akshare", 1000)
        .expect_err("request should fail");

    match err {
        AppError::Upstream(status, _) => assert_eq!(status, 503),
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
