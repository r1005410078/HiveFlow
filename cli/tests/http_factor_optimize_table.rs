use hf_cli::infrastructure::http_client::post_factor_optimize;
use hf_cli::infrastructure::table_renderer::render_factor_optimize_table;
use mockito::Server;

#[test]
fn factor_optimize_table_contains_recommendation_rows() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20", "max_drawdown_60"],
            "constraints": {},
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf factor optimize","status":"ok","advice_only":true,"decision_weight":0,"data":{"factor_names":["momentum_20","inv_volatility_20","max_drawdown_60"],"analysis":{"factor_health":[],"correlation_matrix":{},"coverage":{"symbols":0,"bars":0}},"recommendations":[{"name":"balanced","weights":{"momentum_20":0.4,"inv_volatility_20":0.3,"max_drawdown_60":0.3},"expected_sharpe":1.62,"expected_drawdown":0.19,"score":1.53},{"name":"risk_first","weights":{"momentum_20":0.35,"inv_volatility_20":0.35,"max_drawdown_60":0.3},"expected_sharpe":1.55,"expected_drawdown":0.16,"score":1.47}],"recommended_scheme":"balanced"},"audit":{"generated_at":"2026-04-02T00:00:00+00:00","analysis_period":{"start_date":"2026-01-01","end_date":"2026-04-01"},"g3_review_required":true},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_factor_optimize(
        &server.url(),
        "2026-01-01",
        "2026-04-01",
        &[
            "momentum_20".to_string(),
            "inv_volatility_20".to_string(),
            "max_drawdown_60".to_string(),
        ],
        1000,
    )
    .expect("factor optimize should succeed");

    let table = render_factor_optimize_table(&out).expect("table rendering should succeed");

    assert!(table.contains("因子优化建议"));
    assert!(table.contains("推荐方案"));
    assert!(table.contains("方案"));
    assert!(table.contains("预期Sharpe"));
    assert!(table.contains("预期回撤"));
    assert!(table.contains("权重"));
    assert!(table.contains("balanced"));
    assert!(table.contains("risk_first"));
}
