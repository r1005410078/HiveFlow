use hf_cli::infrastructure::table_renderer::render_sync_run_progress_summary;
use serde_json::json;

#[test]
fn task_progress_table_shows_phase_and_progress_fields() {
    let detail = json!({
        "run_id": "run_001",
        "status": "running",
        "phase": "fetching_bars",
        "progress": {
            "total_symbols": 10,
            "completed_symbols": 3,
            "current_symbol": "600519.SH",
            "total_days": 5,
            "completed_days": 2
        },
        "selection_mode": "symbols",
        "end_date": "2026-04-01",
        "timeframe": "1d",
        "days": 5
    });
    let table = render_sync_run_progress_summary(&detail, false);
    assert!(table.contains("Sync run progress"));
    assert!(table.contains("run_001"));
    assert!(table.contains("fetching_bars"));
    assert!(table.contains("600519.SH"));
    assert!(table.contains("3/10"));
    assert!(table.contains("2/5"));
}
