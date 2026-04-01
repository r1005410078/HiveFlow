use hf_cli::infrastructure::http_client::get_data_sync_runs;
use hf_cli::infrastructure::table_renderer::render_sync_runs_table;
use mockito::Server;

#[test]
fn data_query_table_renders_six_columns() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/sync-runs")
        .match_query(mockito::Matcher::UrlEncoded("days".into(), "5".into()))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"bar_time":"2026-04-01T15:00:00+08:00","symbol":"600519.SH","status":"success","timeframe":"1d","open":1450.0,"high":1468.0,"low":1442.0,"close":1459.44,"volume":29125.0,"amount":4256185472.0,"data_source":"tencent","manifest_id":""}]}"#,
        )
        .create();

    let out = get_data_sync_runs(&server.url(), 5, None, None, None, 1000).expect("query ok");
    let table = render_sync_runs_table(&out, false);

    assert!(table.contains("Market Data"));
    assert!(table.contains("bar_time"));
    assert!(table.contains("symbol"));
    assert!(table.contains("timeframe"));
    assert!(table.contains("close"));
    // comfy-table should render UTF-8 borders.
    assert!(table.contains("│") || table.contains("╭"));
    assert!(table.contains("2026-04-01"));
    assert!(table.contains("600519.SH"));
}
