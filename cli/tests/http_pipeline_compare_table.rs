use hf_cli::infrastructure::http_client::post_pipeline_compare;
use hf_cli::infrastructure::table_renderer::render_pipeline_compare_table;
use mockito::Server;

#[test]
fn pipeline_compare_table_renders_daily_rows_and_summary() {
    let mut server = Server::new();
    let _mock = server
        .mock("POST", "/api/v1/pipeline/compare")
        .match_header("content-type", "application/json")
        .match_body(mockito::Matcher::PartialJson(serde_json::json!({
            "start_date": "2026-03-01",
            "end_date": "2026-03-30",
            "top_n": 5,
        })))
        .with_status(200)
        .with_header("content-type", "application/json")
        .with_body(
            r#"{"schema_version":"1.0.0","command":"hf pipeline compare","run_id":"run_compare_001","status":"ok","generated_at":"2026-04-02T09:00:00+08:00","source":"system","advice_only":false,"decision_weight":1,"data":{"start_date":"2026-03-01","end_date":"2026-03-30","top_n":5,"daily_items":[{"as_of":"2026-03-01","v1":{"top_candidates":[{"symbol":"600519.SH","score":0.71,"rank":1}],"warning_count":1,"min_availability":0.9},"v1_1":{"top_candidates":[{"symbol":"000001.SZ","score":0.74,"rank":1}],"warning_count":0,"min_availability":1.0}},{"as_of":"2026-03-02","v1":{"top_candidates":[{"symbol":"000001.SZ","score":0.66,"rank":1}],"warning_count":0,"min_availability":1.0},"v1_1":{"top_candidates":[{"symbol":"000001.SZ","score":0.76,"rank":1}],"warning_count":0,"min_availability":1.0}}],"summary":{"days":2,"avg_warning_count_v1":0.5,"avg_warning_count_v1_1":0.0,"avg_min_availability_v1":0.95,"avg_min_availability_v1_1":1.0,"top1_symbol_change_days":1}},"warnings":[],"errors":[]}"#,
        )
        .create();

    let out = post_pipeline_compare(&server.url(), "2026-03-01", "2026-03-30", 5, 1000)
        .expect("compare should succeed");
    let table = render_pipeline_compare_table(&out);

    assert!(table.contains("版本对比回放"));
    assert!(table.contains("版本对比汇总"));
    assert!(table.contains("日期"));
    assert!(table.contains("v1_top1"));
    assert!(table.contains("v1.1_top1"));
    assert!(table.contains("v1_warn"));
    assert!(table.contains("v1.1_warn"));
    assert!(table.contains("v1_min_avail"));
    assert!(table.contains("v1.1_min_avail"));
    assert!(table.contains("2026-03-01"));
    assert!(table.contains("600519.SH"));
    assert!(table.contains("000001.SZ"));
    assert!(table.contains("Top1变更天数"));
}
