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
            r#"{"schema_version":"1.0.0","command":"hf pipeline compare","run_id":"run_compare_001","status":"ok","generated_at":"2026-04-02T09:00:00+08:00","source":"system","advice_only":false,"decision_weight":1,"data":{"start_date":"2026-03-01","end_date":"2026-03-30","top_n":5,"daily_items":[{"as_of":"2026-03-01","v1":{"top_candidates":[{"symbol":"600519.SH","score":0.71,"rank":1}],"warning_count":1,"min_availability":0.9},"v1_1":{"top_candidates":[{"symbol":"000001.SZ","score":0.74,"rank":1}],"warning_count":0,"min_availability":1.0}},{"as_of":"2026-03-02","v1":{"top_candidates":[{"symbol":"000001.SZ","score":0.66,"rank":1}],"warning_count":0,"min_availability":1.0},"v1_1":{"top_candidates":[{"symbol":"000001.SZ","score":0.76,"rank":1}],"warning_count":0,"min_availability":1.0}}],"summary":{"days":2,"avg_warning_count_v1":0.5,"avg_warning_count_v1_1":0.0,"avg_min_availability_v1":0.95,"avg_min_availability_v1_1":1.0,"top1_symbol_change_days":1},"analytics":{"return_metrics":{"v1":{"cumulative_return":0.042,"win_rate":0.53,"max_drawdown":0.081,"annualized_volatility":0.19,"sharpe":0.88},"v1_1":{"cumulative_return":0.067,"win_rate":0.58,"max_drawdown":0.073,"annualized_volatility":0.18,"sharpe":1.07},"diff":{"excess_cumulative_return_v1_1_vs_v1":0.025,"excess_sharpe_v1_1_vs_v1":0.19}},"daily_return_series":{"v1":[{"as_of":"2026-03-01","top1_next_day_return":0.0042}],"v1_1":[{"as_of":"2026-03-01","top1_next_day_return":0.0061}]},"group_stability":{"group_key":"industry_market_cap_bucket","items":[{"industry":"Bank","market_cap_bucket":"LARGE","sample_days":8,"v1":{"cumulative_return":0.012,"win_rate":0.5,"sharpe":0.42},"v1_1":{"cumulative_return":0.021,"win_rate":0.63,"sharpe":0.71},"diff":{"excess_cumulative_return":0.009,"excess_sharpe":0.29},"stability_flag":"OK"},{"industry":"Tech","market_cap_bucket":"MID","sample_days":3,"v1":{"cumulative_return":-0.01,"win_rate":0.33,"sharpe":-0.2},"v1_1":{"cumulative_return":0.015,"win_rate":0.67,"sharpe":0.4},"diff":{"excess_cumulative_return":0.025,"excess_sharpe":0.6},"stability_flag":"LOW_SAMPLE"}]}}},"warnings":[],"errors":[]}"#,
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
    assert!(table.contains("收益与风险统计"));
    assert!(table.contains("累计收益"));
    assert!(table.contains("胜率"));
    assert!(table.contains("最大回撤"));
    assert!(table.contains("年化波动"));
    assert!(table.contains("夏普"));
    assert!(table.contains("分组稳定性（industry + market_cap_bucket）"));
    assert!(table.contains("industry"));
    assert!(table.contains("cap_bucket"));
    assert!(table.contains("sample_days"));
    assert!(table.contains("v1_cum"));
    assert!(table.contains("v1.1_cum"));
    assert!(table.contains("diff_cum"));
    assert!(table.contains("flag"));
    assert!(table.contains("Bank"));
    assert!(table.contains("LARGE"));
    assert!(table.contains("LOW_SAMPLE"));
}
