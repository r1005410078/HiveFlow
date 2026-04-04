use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_symbol_names_sync;
use mockito::Server;

#[test]
fn data_symbol_names_sync_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/universes/symbol-names/sync")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "universes": ["csi300", "zz500"],
            "provider": "akshare",
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"provider":"akshare","universes":["csi300","zz500"],"per_universe_symbols":{"csi300":1,"zz500":2},"symbol_names_path":"/q/config/universes/symbol_names.json","updated_at":"2026-04-04T00:00:00+00:00"}"#,
        )
        .create();

    let universes = vec!["csi300".to_string(), "zz500".to_string()];
    let out = post_symbol_names_sync(&server.url(), &universes, "akshare", 1000)
        .expect("symbol names sync should succeed");

    assert_eq!(out["provider"], "akshare");
    assert_eq!(out["universes"], serde_json::json!(["csi300", "zz500"]));
}

#[test]
fn data_symbol_names_sync_omits_universes_when_empty() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/universes/symbol-names/sync")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "provider": "akshare",
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"provider":"akshare","universes":["csi300","zz500","all_a"],"per_universe_symbols":{},"symbol_names_path":null,"updated_at":"2026-04-04T00:00:00+00:00"}"#)
        .create();

    let out = post_symbol_names_sync(&server.url(), &[], "akshare", 1000).expect("ok");
    assert_eq!(out["universes"], serde_json::json!(["csi300", "zz500", "all_a"]));
}

#[test]
fn data_symbol_names_sync_returns_upstream_error() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/v1/market-data/universes/symbol-names/sync")
        .with_status(503)
        .with_header("content-type", "application/json")
        .with_body(r#"{"detail":{"code":"SYMBOL_NAMES_SYNC_PROVIDER_ERROR","message":"no akshare"}}"#)
        .create();

    let err = post_symbol_names_sync(&server.url(), &[], "akshare", 1000).expect_err("should fail");

    match err {
        AppError::Upstream(status, _) => assert_eq!(status, 503),
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
