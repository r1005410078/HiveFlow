use hf_cli::infrastructure::http_client::get_market_data_sync_runs;
use hf_cli::infrastructure::table_renderer::render_sync_runs_table;
use mockito::Server;

#[test]
fn data_query_table_renders_sync_run_metadata_columns() {
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
            r#"{"items":[{"run_id":"run_001","request_id":"req_001","status":"success","days":5,"end_date":"2026-04-01","timeframe":"1d","effective_symbols_count":2,"started_at":"2026-04-01T09:30:00+08:00","finished_at":"2026-04-01T09:31:00+08:00","error_code":null,"error_message":null}]}"#,
        )
        .create();

    let out = get_market_data_sync_runs(&server.url(), 5, Some("1d"), None, None, None, 1000)
        .expect("query ok");
    let table = render_sync_runs_table(&out, false);

    assert!(table.contains("Sync Runs"));
    assert!(table.contains("end_date"));
    assert!(table.contains("timeframe"));
    assert!(table.contains("effective_symbols_count"));
    assert!(table.contains("request_id"));
    // comfy-table should render UTF-8 borders.
    assert!(table.contains("│") || table.contains("╭"));
    assert!(table.contains("2026-04-01"));
    assert!(table.contains("req_001"));
}
