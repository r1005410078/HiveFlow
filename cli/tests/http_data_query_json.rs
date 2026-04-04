use hf_cli::infrastructure::http_client::get_market_data_sync_runs;
use mockito::Server;

/// HTTP client for sync-runs (`hf task list`); filename is historical.
#[test]
fn task_list_client_calls_sync_runs_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/sync-runs")
        .match_query(mockito::Matcher::AllOf(vec![
            mockito::Matcher::UrlEncoded("days".into(), "5".into()),
            mockito::Matcher::UrlEncoded("timeframe".into(), "1d".into()),
            mockito::Matcher::UrlEncoded("status".into(), "success".into()),
            mockito::Matcher::UrlEncoded("request_id".into(), "req_001".into()),
            mockito::Matcher::UrlEncoded("limit".into(), "20".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"run_id":"run_001","request_id":"req_001","status":"success","end_date":"2026-04-01","timeframe":"1d","effective_symbols_count":2}]}"#,
        )
        .create();

    let out = get_market_data_sync_runs(
        &server.url(),
        5,
        Some("1d"),
        Some("success"),
        Some("req_001"),
        Some(20),
        1000,
    )
        .expect("query should succeed");

    assert!(out["items"].is_array());
    assert_eq!(out["items"][0]["run_id"], "run_001");
    assert_eq!(out["items"][0]["request_id"], "req_001");
}
