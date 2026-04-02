use crate::application::requests::PipelineDailyRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_pipeline_daily_table;

pub fn handle(args: PipelineDailyRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_daily(&cfg.server_url, &args.as_of, cfg.timeout_ms)?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_pipeline_daily_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for pipeline daily: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
