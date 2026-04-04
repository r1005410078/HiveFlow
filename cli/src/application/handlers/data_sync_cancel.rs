use crate::application::requests::DataSyncCancelRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_sync_run_cancel;

pub fn handle(args: DataSyncCancelRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = post_sync_run_cancel(&cfg.server_url, &args.run_id, timeout_ms)?;
    print!("{out}");
    Ok(())
}
