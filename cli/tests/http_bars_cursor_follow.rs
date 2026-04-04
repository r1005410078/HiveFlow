//! 单标的 + `follow_cursor_pages` 时应对 `has_more` / `next_cursor_bar_time` 连续请求。

use hf_cli::application::bars_fetch::{
    fetch_bars_merged_items_with_options, BarsFetchOptions,
};
use mockito::{Matcher, Server};

#[test]
fn fetch_bars_merged_follows_cursor_for_single_symbol() {
    let mut server = Server::new();
    let symbols = vec!["600519.SH".to_string()];

    // 后注册的先匹配：先注册「无 cursor」页，再注册带 cursor 的页，避免第二请求被宽松 mock 吃掉。
    let _m1 = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(Matcher::AllOf(vec![
            Matcher::UrlEncoded("timeframe".into(), "1d".into()),
            Matcher::UrlEncoded("limit".into(), "1".into()),
            Matcher::UrlEncoded("symbols".into(), "600519.SH".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"600519.SH","bar_time":"2026-04-02T15:00:00+08:00","open":1,"high":1,"low":1,"close":1}],"has_more":true,"next_cursor_bar_time":"2026-04-01T15:00:00+08:00","next_cursor_symbol":"600519.SH"}"#,
        )
        .expect(1)
        .create();

    let _m2 = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(Matcher::AllOf(vec![
            Matcher::UrlEncoded("cursor_symbol".into(), "600519.SH".into()),
            Matcher::Regex("cursor_bar_time=".into()),
        ]))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"600519.SH","bar_time":"2026-04-01T15:00:00+08:00","open":2,"high":2,"low":2,"close":2}],"has_more":false}"#,
        )
        .expect(1)
        .create();

    let merged = fetch_bars_merged_items_with_options(
        &server.url(),
        &symbols,
        Some("1d"),
        None,
        None,
        Some(1),
        1000,
        BarsFetchOptions {
            follow_cursor_pages: true,
            ..Default::default()
        },
    )
    .expect("merged with cursor");

    assert_eq!(merged.len(), 2);
}
