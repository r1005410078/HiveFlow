use hf_cli::infrastructure::http_client::post_pretrade_check;
use hf_cli::infrastructure::table_renderer::render_pretrade_check_table;
use mockito::Server;
use serde_json::json;

#[test]
fn pretrade_check_table_contains_overall_tradable() {
    let payload = json!({
        "schema_version": "1.0.0",
        "command": "hf pretrade check",
        "run_id": "r1",
        "status": "ok",
        "generated_at": "2026-04-01T10:00:00+00:00",
        "source": "system",
        "advice_only": false,
        "decision_weight": 1,
        "data": {
            "as_of": "2026-04-01",
            "notional": 1000000.0,
            "overall_tradable": true,
            "total_impact_bp": 5.5,
            "orders": [{
                "symbol": "600519.SH",
                "target_weight": 1.0,
                "target_notional": 1000000.0,
                "adv": 800000000.0,
                "participation_rate": 0.00125,
                "sigma": 0.18,
                "impact_bp": 5.5,
                "tradable": true
            }]
        },
        "warnings": [],
        "errors": []
    });
    let table = render_pretrade_check_table(&payload);
    assert!(table.contains("overall_tradable: YES"));
    assert!(table.contains("600519.SH"));
    assert!(table.contains("total_impact:"));
}

#[test]
fn post_pretrade_check_mock_server_round_trip() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf pretrade check","run_id":"r1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"as_of":"2026-04-01","notional":1000000.0,"overall_tradable":true,"total_impact_bp":1.0,"orders":[]},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock("POST", "/api/v1/pretrade/check")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(body)
        .create();

    let out = post_pretrade_check(
        &server.url(),
        "2026-04-01",
        json!({"600519.SH": 0.5, "300750.SZ": 0.5}),
        1_000_000.0,
        3000,
    )
    .expect("http");
    assert_eq!(out["command"], "hf pretrade check");
    assert_eq!(out["data"]["as_of"], "2026-04-01");
}
