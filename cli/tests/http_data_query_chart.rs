use hf_cli::infrastructure::chart_renderer::render_sync_runs_chart_with_capability;
use serde_json::json;

#[test]
fn data_query_chart_returns_error_without_utf8_terminal() {
    let payload = json!({
        "items": [
            {"bar_time":"2026-04-01T09:30:00+08:00","symbol":"600519.SH","close":1450.0},
            {"bar_time":"2026-04-01T09:31:00+08:00","symbol":"600519.SH","close":1459.0}
        ]
    });
    let res = render_sync_runs_chart_with_capability(&payload, false, "600519.SH", Some("000300.SH"));
    assert!(res.is_err());
}

#[test]
fn data_query_chart_renders_line_chart_in_utf8_terminal() {
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
    // textplots output should include unicode plotting glyphs (render may vary by version).
    assert!(chart.chars().any(|c| !c.is_ascii()));
}

#[test]
fn data_query_chart_single_point_uses_readable_fallback() {
    let payload = json!({
        "items": [
            {"bar_time":"2026-04-01T15:00:00+08:00","symbol":"600519.SH","close":1459.44}
        ]
    });
    let chart = render_sync_runs_chart_with_capability(&payload, true, "600519.SH", Some("000300.SH"))
        .expect("chart should be rendered");
    assert!(chart.contains("sample too small for line chart"));
    assert!(chart.contains("point: ●"));
}
