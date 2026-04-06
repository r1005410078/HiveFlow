use crate::application::requests::MonitorHealthReportRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_health_report;
use crate::infrastructure::table_renderer::render_monitor_health_report_table;

pub fn handle(args: MonitorHealthReportRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let result = get_health_report(&cfg.server_url, &args.as_of, timeout_ms)?;

    if args.output == "json" {
        println!("{}", serde_json::to_string_pretty(&result).unwrap_or_default());
    } else {
        print!("{}", render_monitor_health_report_table(&result));
    }
    Ok(())
}
