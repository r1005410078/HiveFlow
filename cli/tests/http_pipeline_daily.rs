use hf_cli::infrastructure::http_client::post_daily;
use hf_cli::error::AppError;
use mockito::Server;

#[test]
fn pipeline_daily_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/daily")
        .match_header("content-type", "application/json")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf pipeline daily","status":"ok","data":{"as_of":"2026-04-01","execution_plan":{"orders":[]}},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_daily(&server.url(), "2026-04-01", 1000).expect("http call should succeed");

    assert_eq!(out["status"], "ok");
    assert_eq!(out["data"]["as_of"], "2026-04-01");
    assert_eq!(out["data"]["execution_plan"]["orders"].as_array().map(|v| v.len()), Some(0));
}

#[test]
fn pipeline_daily_returns_upstream_error_for_non_json_error_body() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/daily")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let err = post_daily(&server.url(), "2026-04-01", 1000).expect_err("request should fail");

    match err {
        AppError::Upstream(status, body) => {
            assert_eq!(status, 502);
            assert_eq!(body["raw_body"], "bad gateway");
        }
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
