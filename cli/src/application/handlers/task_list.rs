use crate::application::requests::TaskListRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_market_data_sync_runs;
use crate::infrastructure::table_renderer::render_sync_runs_table;

pub fn handle(args: TaskListRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = get_market_data_sync_runs(
        &cfg.server_url,
        args.days,
        Some(args.timeframe.as_str()),
        args.status.as_deref(),
        args.request_id.as_deref(),
        args.limit,
        timeout_ms,
    )?;

    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_sync_runs_table(&out, args.verbose);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for task list: {other} (expected: json|table)"
            )));
        }
    }

    Ok(())
}
