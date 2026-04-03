use hf_cli::application::handlers::factor_replay::run_replay;
use hf_cli::application::requests::FactorReplayRequest;
use mockito::Server;

#[test]
fn factor_replay_runs_daily_evaluate_and_builds_summary() {
    let mut server = Server::new();

    let _m1 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-04-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
            "correlation_threshold": 0.7
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"pass","blocking_reasons":[],"watch_items":[]},"correlation_analysis":{"alert_count":0},"top_combinations":{"items":[{"factors":["momentum_20","inv_volatility_20"]}]}}}"#)
        .create();

    let _m2 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-04-02",
            "end_date": "2026-04-02",
            "factor_names": ["momentum_20", "inv_volatility_20"],
            "constraints": {},
            "correlation_threshold": 0.7
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"watch","blocking_reasons":[],"watch_items":["alert_count_watch:2"]},"correlation_analysis":{"alert_count":2},"top_combinations":{"items":[{"factors":["momentum_20","max_drawdown_60"]}]}}}"#)
        .create();

    let req = FactorReplayRequest {
        start_date: "2026-04-01".to_string(),
        end_date: "2026-04-02".to_string(),
        factor_names: vec!["momentum_20".to_string(), "inv_volatility_20".to_string()],
        correlation_threshold: Some(0.7),
        output: "json".to_string(),
    };

    let out = run_replay(&server.url(), 1000, &req).expect("replay should succeed");

    assert_eq!(out["summary"]["days"], 2);
    assert_eq!(out["summary"]["error_days"], 0);
    assert_eq!(out["summary"]["pass_days"], 1);
    assert_eq!(out["summary"]["watch_days"], 1);
    assert_eq!(out["summary"]["fail_days"], 0);
    assert_eq!(out["summary"]["top1_change_days"], 1);
    assert_eq!(out["daily_items"].as_array().unwrap().len(), 2);
}

#[test]
fn factor_replay_counts_fetch_errors_separately() {
    let mut server = Server::new();

    let _m1 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(r#"{"status":"ok","data":{"release_gate":{"status":"fail","blocking_reasons":["no_top_combinations"],"watch_items":[]},"correlation_analysis":{"alert_count":0},"top_combinations":{"items":[]}}}"#)
        .create();

    let _m2 = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .with_status(502)
        .with_header("content-type", "text/plain")
        .with_body("bad gateway")
        .create();

    let req = FactorReplayRequest {
        start_date: "2026-04-01".to_string(),
        end_date: "2026-04-02".to_string(),
        factor_names: vec!["momentum_20".to_string()],
        correlation_threshold: None,
        output: "json".to_string(),
    };

    let out = run_replay(&server.url(), 1000, &req).expect("replay should still succeed");

    assert_eq!(out["summary"]["days"], 2);
    assert_eq!(out["summary"]["error_days"], 1);
    assert_eq!(out["daily_items"][1]["fetch_status"], "error");
    assert_eq!(out["daily_items"][1]["release_gate_status"], "unknown");
}
