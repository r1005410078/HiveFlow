use crate::application::requests::PipelineDailyRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;

pub fn handle(args: PipelineDailyRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_daily(&cfg.server_url, &args.as_of, cfg.timeout_ms)?;
    print!("{out}");
    Ok(())
}
