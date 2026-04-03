use crate::application::requests::DataUniverseSyncRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_data_universe_sync;

pub fn handle(args: DataUniverseSyncRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = post_data_universe_sync(
        &cfg.server_url,
        &args.universe,
        &args.provider,
        timeout_ms,
    )?;
    print!("{out}");
    Ok(())
}
