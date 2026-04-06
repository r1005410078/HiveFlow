use hf_cli::infrastructure::http_client::{probe_openapi_json, OpenapiProbeOutcome};

use mockito::Server;

#[test]
fn probe_openapi_json_200_ok() {
    let mut server = Server::new();
    let _m = server
        .mock("GET", "/openapi.json")
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body("{}")
        .create();

    let out = probe_openapi_json(&server.url(), 3000);
    assert_eq!(
        out,
        OpenapiProbeOutcome {
            reachable: true,
            http_status: Some(200),
            error_message: None,
        }
    );
}

#[test]
fn probe_openapi_json_non_200_not_reachable() {
    let mut server = Server::new();
    let _m = server
        .mock("GET", "/openapi.json")
        .with_status(503)
        .with_body("unavailable")
        .create();

    let out = probe_openapi_json(&server.url(), 3000);
    assert!(!out.reachable);
    assert_eq!(out.http_status, Some(503));
    assert_eq!(out.error_message, Some("HTTP 503".to_string()));
}
