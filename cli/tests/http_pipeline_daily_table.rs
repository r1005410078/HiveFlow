use hf_cli::infrastructure::http_client::post_daily;
use hf_cli::infrastructure::table_renderer::render_pipeline_daily_table;
use mockito::Server;

#[test]
fn pipeline_daily_table_renders_top_candidates_and_factor_availability() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/daily")
        .match_header("content-type", "application/json")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf pipeline daily","run_id":"run_001","status":"ok","generated_at":"2026-04-01T09:00:00+08:00","source":"system","advice_only":false,"decision_weight":1,"data":{"as_of":"2026-04-01","data_manifest_id":"dm_001","factor_snapshot":{"factor_version":"l2-basic-v1.1","factor_names":["momentum_20","inv_volatility_20","turnover_rate","max_drawdown_60","trend_stability_20","relative_strength_vs_index"],"coverage_rate":1.0,"rows":[]},"l2_decision":{"schema_version":"1.0","generated_at":"2026-04-01T01:00:00+00:00","producer_version":"quant-l2","score_version":"l2-score-v1.1","universe_size":2,"top_candidates":[{"symbol":"600519.SH","score":0.8123,"rank":1},{"symbol":"000001.SZ","score":0.4231,"rank":2}],"factor_availability":[{"factor_name":"momentum_20","present_count":2,"missing_count":0,"availability_rate":1.0},{"factor_name":"trend_stability_20","present_count":1,"missing_count":1,"availability_rate":0.5}],"score_breakdown":[]},"execution_plan":{"orders":[]}},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_daily(&server.url(), "2026-04-01", 1000).expect("http call should succeed");
    let table = render_pipeline_daily_table(&out);

    assert!(table.contains("Pipeline Daily Summary"));
    assert!(table.contains("Top Candidates"));
    assert!(table.contains("Factor Availability"));
    assert!(table.contains("l2-score-v1.1"));
    assert!(table.contains("600519.SH"));
    assert!(table.contains("trend_stability_20"));
}

