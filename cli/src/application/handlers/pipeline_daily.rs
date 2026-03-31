use crate::cmd::pipeline::{PipelineArgs, PipelineSubcommand};
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;

pub fn handle(args: PipelineArgs) -> Result<(), AppError> {
    match args.command {
        PipelineSubcommand::Daily(daily) => {
            let cfg = load_default_config()?;
            let out = http_client::post_daily(&cfg.server_url, &daily.as_of, cfg.timeout_ms)?;
            print!("{out}");
            Ok(())
        }
    }
}
