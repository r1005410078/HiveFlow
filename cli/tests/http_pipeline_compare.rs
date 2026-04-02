use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_pipeline_compare;
use mockito::Server;

#[test]
fn pipeline_compare_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/compare")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-03-01",
            "end_date": "2026-03-30",
            "top_n": 5,
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf pipeline compare","status":"ok","data":{"start_date":"2026-03-01","end_date":"2026-03-30","top_n":5,"daily_items":[],"summary":{"days":0,"avg_warning_count_v1":0.0,"avg_warning_count_v1_1":0.0,"avg_min_availability_v1":0.0,"avg_min_availability_v1_1":0.0,"top1_symbol_change_days":0}},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_pipeline_compare(&server.url(), "2026-03-01", "2026-03-30", 5, 1000)
        .expect("compare should succeed");

    assert_eq!(out["status"], "ok");
    assert_eq!(out["command"], "hf pipeline compare");
    assert_eq!(out["data"]["start_date"], "2026-03-01");
    assert_eq!(out["data"]["end_date"], "2026-03-30");
    assert_eq!(out["data"]["top_n"], 5);
}

#[test]
fn pipeline_compare_returns_upstream_error_for_non_json_error_body() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/compare")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let err = post_pipeline_compare(&server.url(), "2026-03-01", "2026-03-30", 5, 1000)
        .expect_err("request should fail");

    match err {
        AppError::Upstream(status, body) => {
            assert_eq!(status, 502);
            assert_eq!(body["raw_body"], "bad gateway");
        }
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
