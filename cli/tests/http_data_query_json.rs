use hf_cli::infrastructure::http_client::get_data_sync_runs;
use mockito::Server;

#[test]
fn data_query_json_calls_sync_runs_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/sync-runs")
        .match_query(mockito::Matcher::AllOf(vec![
            mockito::Matcher::UrlEncoded("days".into(), "5".into()),
            mockito::Matcher::UrlEncoded("timeframe".into(), "1d".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"run_id":"run_001","date":"2026-04-01","status":"success","timeframe":"1d","symbols_count":2,"manifest_id":"mf_001"}]}"#,
        )
        .create();

    let out = get_data_sync_runs(&server.url(), 5, Some("1d"), None, None, 1000)
        .expect("query should succeed");

    assert!(out["items"].is_array());
    assert_eq!(out["items"][0]["run_id"], "run_001");
}

