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
            r#"{"items":[{"run_id":"run_1234567890abcdef","date":"2026-04-01","status":"success","timeframe":"1d","symbols_count":2,"manifest_id":"mf_1234567890abcdef"}]}"#,
        )
        .create();

    let out = get_data_sync_runs(&server.url(), 5, None, None, None, 1000).expect("query ok");
    let table = render_sync_runs_table(&out, false);

    assert!(table.contains("date | status | timeframe | symbols_count | run_id | manifest_id"));
    assert!(table.contains("2026-04-01 | success | 1d | 2"));
}

