use hf_cli::infrastructure::http_client::get_health_report;
use hf_cli::infrastructure::table_renderer::render_monitor_health_report_table;
use mockito::Server;

#[test]
fn monitor_health_report_json_envelope_round_trip() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf monitor health-report","run_id":"hr_1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"as_of":"2026-04-01","overall_rating":"green","factor_health":{"total":1,"ok_count":1,"warn_count":0,"miss_count":0,"details":[]},"signal_health":{"coverage_rate":0.89,"composite_score_mean":0.1,"composite_score_std":0.2,"status":"ok"},"risk_health":{"regime":"normal","triggered_rules":[],"status":"ok"},"trend":null,"run_daily_warnings":[]},"warnings":[],"errors":[]}"#;
    let _mock = server
        .mock("GET", "/v1/monitor/health-report")
        .match_query(mockito::Matcher::UrlEncoded("as_of".into(), "2026-04-01".into()))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(body)
        .create();

    let out = get_health_report(&server.url(), "2026-04-01", 3000).expect("http");
    assert_eq!(out["command"], "hf monitor health-report");
    assert_eq!(out["data"]["overall_rating"], "green");
}

#[test]
fn monitor_health_report_table_contains_overall() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf monitor health-report","run_id":"hr_1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"as_of":"2026-04-01","overall_rating":"green","factor_health":{"total":1,"ok_count":1,"warn_count":0,"miss_count":0,"details":[]},"signal_health":{"coverage_rate":0.89,"composite_score_mean":0.1,"composite_score_std":0.2,"status":"ok"},"risk_health":{"regime":"normal","triggered_rules":[],"status":"ok"},"trend":null,"run_daily_warnings":[]},"warnings":[],"errors":[]}"#;
    let _mock = server
        .mock("GET", "/v1/monitor/health-report")
        .match_query(mockito::Matcher::UrlEncoded("as_of".into(), "2026-04-01".into()))
        .with_status(200)
        .with_body(body)
        .create();

    let out = get_health_report(&server.url(), "2026-04-01", 3000).expect("http");
    let table = render_monitor_health_report_table(&out);
    assert!(table.contains("overall: GREEN"));
    assert!(table.contains("Factor Health"));
    assert!(table.contains("Signal Health"));
}
