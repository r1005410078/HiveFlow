use hf_cli::infrastructure::chart_renderer::render_sync_runs_chart;
use serde_json::json;

#[test]
fn data_query_chart_returns_error_without_utf8_terminal() {
    let previous = std::env::var("LANG").ok();
    // Non UTF-8 locale to force fallback path in renderer.
    unsafe { std::env::set_var("LANG", "C"); }

    let payload = json!({
        "items": [
            {"date":"2026-04-01","status":"success","symbols_count":2},
            {"date":"2026-04-01","status":"failed","symbols_count":1}
        ]
    });
    let res = render_sync_runs_chart(&payload);
    assert!(res.is_err());

    if let Some(v) = previous {
        unsafe { std::env::set_var("LANG", v); }
    }
}

