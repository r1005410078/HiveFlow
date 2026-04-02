use hf_cli::infrastructure::chart_renderer::render_sync_runs_chart_with_capability;
use serde_json::json;

#[test]
fn data_bars_chart_renders_line_chart_for_bars_payload() {
    let payload = json!({
        "items": [
            {"bar_time":"2026-03-29T15:00:00+08:00","symbol":"600519.SH","close":1400.0},
            {"bar_time":"2026-03-30T15:00:00+08:00","symbol":"600519.SH","close":1420.0},
            {"bar_time":"2026-03-31T15:00:00+08:00","symbol":"600519.SH","close":1450.0},
            {"bar_time":"2026-04-01T15:00:00+08:00","symbol":"600519.SH","close":1459.0}
        ]
    });

    let chart = render_sync_runs_chart_with_capability(&payload, true, "600519.SH", Some("000300.SH"))
        .expect("chart should be rendered");

    assert!(chart.contains("Price Chart (textplots)"));
    assert!(chart.contains("600519.SH"));
    assert!(chart.contains("Compact Trend:"));
    assert!(chart.contains("Close Price"));
    assert!(chart.chars().any(|c| !c.is_ascii()));
}
