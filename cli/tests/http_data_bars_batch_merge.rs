//! 超过 `SYMBOL_BATCH`（30）只标的时，`fetch_bars_merged_items` 应分多批请求并合并排序。
//!
//! 注意：mockito 的 `UrlEncoded` + `AllOf` 无法表达多个同名 `symbols` 参数（`serde_urlencoded`
//! 解析为 `HashMap` 会丢重复键），因此这里用 `Matcher::Exact` 匹配整段 query。

use hf_cli::application::bars_fetch::{fetch_bars_merged_items, SYMBOL_BATCH};
use mockito::{Matcher, Server};

fn bars_query_exact(symbols: &[String]) -> String {
    let mut q =
        "timeframe=1d&start_date=2026-04-01&end_date=2026-04-01&limit=200".to_string();
    for s in symbols {
        q.push_str("&symbols=");
        q.push_str(s);
    }
    q
}

#[test]
fn fetch_bars_merged_splits_into_two_http_requests_when_over_batch_size() {
    assert!(SYMBOL_BATCH < 31, "test assumes batch size < 31");

    let symbols: Vec<String> = (0..31).map(|i| format!("B{i:03}")).collect();
    let batch1: Vec<String> = symbols[..SYMBOL_BATCH].to_vec();
    let batch2: Vec<String> = symbols[SYMBOL_BATCH..].to_vec();

    let mut server = Server::new();

    let m1 = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(Matcher::Exact(bars_query_exact(&batch1)))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"B000","bar_time":"2026-04-01T00:00:00Z","open":1.0,"high":1.0,"low":1.0,"close":1.0}]}"#,
        )
        .expect(1)
        .create();

    let m2 = server
        .mock("GET", "/v1/market-data/bars")
        .match_query(Matcher::Exact(bars_query_exact(&batch2)))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"items":[{"symbol":"B030","bar_time":"2026-04-02T00:00:00Z","open":2.0,"high":2.0,"low":2.0,"close":2.0}]}"#,
        )
        .expect(1)
        .create();

    let merged = fetch_bars_merged_items(
        &server.url(),
        &symbols,
        Some("1d"),
        Some("2026-04-01"),
        Some("2026-04-01"),
        Some(200),
        5000,
    )
    .expect("merged fetch should succeed");

    assert_eq!(merged.len(), 2);
    assert_eq!(
        merged[0].get("symbol").and_then(|v| v.as_str()),
        Some("B000")
    );
    assert_eq!(
        merged[1].get("symbol").and_then(|v| v.as_str()),
        Some("B030")
    );

    m1.assert();
    m2.assert();
}
