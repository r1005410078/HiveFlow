use hf_cli::infrastructure::table_renderer::render_factor_replay_table;

#[test]
fn factor_replay_table_renders_summary_and_daily_rows() {
    let payload = serde_json::json!({
        "summary": {
            "days": 3,
            "error_days": 1,
            "pass_days": 1,
            "watch_days": 1,
            "fail_days": 0,
            "avg_alert_count": 1.0,
            "top1_change_days": 1
        },
        "daily_items": [
            {
                "as_of": "2026-04-01",
                "fetch_status": "ok",
                "release_gate_status": "pass",
                "alert_count": 0,
                "top1_factors": ["momentum_20", "inv_volatility_20"]
            },
            {
                "as_of": "2026-04-02",
                "fetch_status": "ok",
                "release_gate_status": "watch",
                "alert_count": 2,
                "top1_factors": ["momentum_20", "max_drawdown_60"]
            },
            {
                "as_of": "2026-04-03",
                "fetch_status": "error",
                "release_gate_status": "unknown",
                "alert_count": 0,
                "top1_factors": [],
                "error_message": "bad gateway"
            }
        ]
    });

    let table = render_factor_replay_table(&payload);

    assert!(table.contains("因子回放汇总"));
    assert!(table.contains("逐日回放明细"));
    assert!(table.contains("error_days"));
    assert!(table.contains("release_gate_status"));
    assert!(table.contains("momentum_20+inv_volatility_20"));
    assert!(table.contains("2026-04-03"));
    assert!(table.contains("unknown"));
}
