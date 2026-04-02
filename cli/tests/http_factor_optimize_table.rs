use hf_cli::infrastructure::http_client::post_factor_optimize;
use hf_cli::infrastructure::table_renderer::render_factor_optimize_table;
use mockito::Server;

#[test]
fn factor_optimize_table_contains_recommendation_rows() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/factor-optimization/evaluate")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::JsonString(
            serde_json::json!({
            "start_date": "2026-01-01",
            "end_date": "2026-04-01",
            "factor_names": ["momentum_20", "inv_volatility_20", "max_drawdown_60"],
            "constraints": {},
        })
            .to_string(),
        ))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf factor optimize","status":"ok","advice_only":true,"decision_weight":0,"data":{"factor_names":["momentum_20","inv_volatility_20","max_drawdown_60"],"analysis":{"factor_health":[],"correlation_matrix":{},"coverage":{"symbols":0,"bars":0}},"correlation_analysis":{"threshold":0.7,"alerts":[{"factor_a":"momentum_20","factor_b":"max_drawdown_60","correlation":0.83,"severity":"high","suggestion":"降低弱势因子权重或替换"}],"alert_count":1},"report":{"matrix_10d":[{"dimension":"IC","value":"0.12 ✅"},{"dimension":"Sharpe","value":"1.62 ✅"},{"dimension":"Max Drawdown","value":"0.19"},{"dimension":"Correlation Redundancy","value":"1"},{"dimension":"Coverage","value":"symbols=10 bars=800"},{"dimension":"Stability","value":"N/A"},{"dimension":"Data Quality","value":"N/A"},{"dimension":"Risk Contribution","value":"0.41"},{"dimension":"Incremental Value","value":"N/A"},{"dimension":"Operational Readiness","value":"G3 checklist required"}],"summary":{"recommended_scheme":"balanced","key_findings":["max_drawdown_60 与 momentum_20 高相关"]},"g3_checklist":[{"item":"风控组评审","checked":false},{"item":"合规组审核","checked":true}]},"recommendations":[{"name":"balanced","weights":{"momentum_20":0.4,"inv_volatility_20":0.3,"max_drawdown_60":0.3},"expected_sharpe":1.62,"expected_drawdown":0.19,"score":1.53},{"name":"risk_first","weights":{"momentum_20":0.35,"inv_volatility_20":0.35,"max_drawdown_60":0.3},"expected_sharpe":1.55,"expected_drawdown":0.16,"score":1.47}],"recommended_scheme":"balanced"},"audit":{"generated_at":"2026-04-02T00:00:00+00:00","analysis_period":{"start_date":"2026-01-01","end_date":"2026-04-01"},"g3_review_required":true},"warnings":[],"errors":[]}"#,
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
        None,
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
    assert!(table.contains("相关性告警"));
    assert!(table.contains("10维评估摘要"));
    assert!(table.contains("severity"));
    assert!(table.contains("correlation"));
    assert!(table.contains("IC"));
    assert!(table.contains("G3 checklist"));
    assert!(table.contains("balanced"));
    assert!(table.contains("risk_first"));
}
