use crate::application::handlers::data_sync::poll_sync_progress;
use crate::application::requests::DataSyncRetryFailedRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_sync_run_retry_failed;

pub fn handle(args: DataSyncRetryFailedRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = post_sync_run_retry_failed(&cfg.server_url, &args.from_run_id, timeout_ms)?;

    let is_async = out.get("run_id").is_some()
        && out.get("status").and_then(|s| s.as_str()) == Some("running");

    if is_async && !args.no_wait {
        let run_id = out["run_id"].as_str().unwrap_or("unknown").to_string();
        poll_sync_progress(&cfg.server_url, &run_id, timeout_ms, 1500)
    } else {
        print!("{out}");
        Ok(())
    }
}
