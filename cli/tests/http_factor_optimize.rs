use hf_cli::error::AppError;
use hf_cli::infrastructure::http_client::post_factor_optimize;
use mockito::Server;

#[test]
fn factor_optimize_calls_http_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::JsonString(
            serde_json::json!({
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
        })
            .to_string(),
        ))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf factor optimize","status":"ok","advice_only":true,"decision_weight":0,"data":{"factor_names":["momentum_20","inv_volatility_20"],"analysis":{"factor_health":[],"correlation_matrix":{},"coverage":{"symbols":0,"bars":0}},"recommendations":[],"recommended_scheme":null},"audit":{"generated_at":"2026-04-02T00:00:00+00:00","analysis_period":{"start_date":"2026-01-01","end_date":"2026-04-01"},"g3_review_required":true},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_factor_optimize(
        &server.url(),
        "2026-01-01",
        "2026-04-01",
        &["momentum_20".to_string(), "inv_volatility_20".to_string()],
        None,
        1000,
    )
    .expect("factor optimize should succeed");

    assert_eq!(out["status"], "ok");
    assert_eq!(out["command"], "hf factor optimize");
    assert_eq!(out["advice_only"], true);
    assert_eq!(out["decision_weight"], 0);
}

#[test]
fn factor_optimize_transmits_optional_correlation_threshold() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::JsonString(
            serde_json::json!({
                "start_date": "2026-01-01",
                "end_date": "2026-04-01",
                "factor_names": ["momentum_20", "inv_volatility_20"],
                "constraints": {},
                "correlation_threshold": 0.72,
            })
            .to_string(),
        ))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf factor optimize","status":"ok","advice_only":true,"decision_weight":0,"data":{"factor_names":["momentum_20","inv_volatility_20"],"analysis":{"factor_health":[],"correlation_matrix":{},"coverage":{"symbols":0,"bars":0}},"recommendations":[],"recommended_scheme":null},"audit":{"generated_at":"2026-04-02T00:00:00+00:00","analysis_period":{"start_date":"2026-01-01","end_date":"2026-04-01"},"g3_review_required":true},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_factor_optimize(
        &server.url(),
        "2026-01-01",
        "2026-04-01",
        &["momentum_20".to_string(), "inv_volatility_20".to_string()],
        Some(0.72),
        1000,
    )
    .expect("factor optimize should succeed");

    assert_eq!(out["status"], "ok");
    assert_eq!(out["command"], "hf factor optimize");
}

#[test]
fn factor_optimize_returns_upstream_error_for_non_json_error_body() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let err = post_factor_optimize(
        &server.url(),
        "2026-01-01",
        "2026-04-01",
        &["momentum_20".to_string()],
        None,
        1000,
    )
    .expect_err("request should fail");

    match err {
        AppError::Upstream(status, body) => {
            assert_eq!(status, 502);
            assert_eq!(body["raw_body"], "bad gateway");
        }
        other => panic!("expected AppError::Upstream, got {other}"),
    }
}
