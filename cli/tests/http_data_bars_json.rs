use hf_cli::infrastructure::http_client::get_market_data_bars;
use mockito::Server;

#[test]
fn data_bars_json_calls_bars_endpoint() {
    let mut server = Server::new();
    let _mock = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(mockito::Matcher::AllOf(vec![
            mockito::Matcher::UrlEncoded("symbols".into(), "600519.SH".into()),
            mockito::Matcher::UrlEncoded("timeframe".into(), "1d".into()),
            mockito::Matcher::UrlEncoded("start_date".into(), "2026-04-01".into()),
            mockito::Matcher::UrlEncoded("end_date".into(), "2026-04-01".into()),
            mockito::Matcher::UrlEncoded("limit".into(), "200".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"600519.SH","timeframe":"1d","bar_time":"2026-04-01T15:00:00+08:00","open":1450.0,"high":1468.0,"low":1442.0,"close":1459.44,"volume":29125.0,"amount":4256185472.0,"data_source":"tencent"}]}"#,
        )
        .create();

    let out = get_market_data_bars(
        &server.url(),
        Some(&["600519.SH".to_string()]),
        Some("1d"),
        Some("2026-04-01"),
        Some("2026-04-01"),
        Some(200),
        1000,
    )
    .expect("bars query should succeed");

    assert!(out["items"].is_array());
    assert_eq!(out["items"][0]["symbol"], "600519.SH");
    assert_eq!(out["items"][0]["close"], 1459.44);
}
