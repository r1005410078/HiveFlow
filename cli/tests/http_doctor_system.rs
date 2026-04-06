use hf_cli::infrastructure::http_client::get_system_doctor;
use mockito::Server;

#[test]
fn get_system_doctor_parses_envelope() {
    let body = r#"{"schema_version":"1.0.0","command":"hf doctor","run_id":"r1","status":"ok","generated_at":"2026-04-06T12:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"producer_version":"quant-system-doctor-v1","db":{"reachable":false,"error":"NO_DB_CONFIG"},"sync":{"window_days":7,"runs_returned":0,"by_status":{},"latest":null,"has_running":false},"positions":{"snapshot_as_of":null,"symbol_count":0,"total_notional":0.0,"has_positions":false,"error":null}},"warnings":[],"errors":[]}"#;
    let mut server = Server::new();
    let _m = server
        .mock("GET", "/v1/system/doctor")
        .match_query(mockito::Matcher::UrlEncoded("sync_days".into(), "7".into()))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(body)
        .create();

    let out = get_system_doctor(&server.url(), 7, 3000).expect("http");
    assert_eq!(out["command"], "hf doctor");
    assert_eq!(out["data"]["db"]["reachable"], false);
}
