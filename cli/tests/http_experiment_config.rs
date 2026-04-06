use hf_cli::infrastructure::http_client::{
    get_experiment_config_detail, get_experiment_config_list, post_experiment_config_snapshot,
};
use hf_cli::infrastructure::table_renderer::{
    render_experiment_config_get_table, render_experiment_config_list_table,
    render_experiment_config_snapshot_table,
};
use mockito::Server;

#[test]
fn experiment_config_snapshot_json_round_trip() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf config snapshot","run_id":"cfg_1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"config_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","params_count":33,"note":"t","created_at":"2026-04-01T10:00:00+00:00"},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock("POST", "/api/v1/experiment/config/snapshot")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(body)
        .create();

    let out = post_experiment_config_snapshot(&server.url(), "t", 3000).expect("http");
    assert_eq!(out["command"], "hf config snapshot");
    assert_eq!(out["data"]["params_count"], 33);
}

#[test]
fn experiment_config_snapshot_table_contains_config_id() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf config snapshot","run_id":"cfg_1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"config_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","params_count":33,"note":"t","created_at":"2026-04-01T10:00:00+00:00"},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock("POST", "/api/v1/experiment/config/snapshot")
        .with_status(200)
        .with_body(body)
        .create();

    let out = post_experiment_config_snapshot(&server.url(), "t", 3000).expect("http");
    let table = render_experiment_config_snapshot_table(&out);
    assert!(table.contains("config_id:"));
    assert!(table.contains("params: 33"));
}

#[test]
fn experiment_config_list_table_has_header() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf config list","run_id":"l1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"configs":[{"config_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","params_count":33,"note":null,"created_at":"x","layers":["l2"]}]},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock("GET", "/api/v1/experiment/configs")
        .match_query(mockito::Matcher::UrlEncoded("limit".into(), "20".into()))
        .with_status(200)
        .with_body(body)
        .create();

    let out = get_experiment_config_list(&server.url(), None, 20, 3000).expect("http");
    let table = render_experiment_config_list_table(&out);
    assert!(table.contains("CONFIG ID"));
}

#[test]
fn experiment_config_get_table_has_layer_column() {
    let mut server = Server::new();
    let body = r#"{"schema_version":"1.0.0","command":"hf config get","run_id":"g1","status":"ok","generated_at":"2026-04-01T10:00:00+00:00","source":"system","advice_only":false,"decision_weight":1,"data":{"config_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","note":"n","created_at":"x","params":[{"layer":"l5.5","param_key":"eta","param_value":0.1}]},"warnings":[],"errors":[]}"#;
    let _m = server
        .mock(
            "GET",
            "/api/v1/experiment/configs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )
        .with_status(200)
        .with_body(body)
        .create();

    let out =
        get_experiment_config_detail(&server.url(), "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", 3000)
            .expect("http");
    let table = render_experiment_config_get_table(&out);
    assert!(table.contains("LAYER"));
    assert!(table.contains("eta"));
}
