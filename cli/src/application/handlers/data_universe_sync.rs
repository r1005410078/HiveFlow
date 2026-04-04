use crate::application::handlers::data_sync::{poll_sync_progress, sync_run_async_accepted};
use crate::application::requests::DataUniverseSyncRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_data_universe_sync;

pub fn handle(args: DataUniverseSyncRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let poll_interval = args.poll_interval_ms.unwrap_or(1500);
    let value = post_data_universe_sync(
        &cfg.server_url,
        &args.universe,
        &args.provider,
        timeout_ms,
    )?;

    if sync_run_async_accepted(&value) {
        if args.wait {
            let run_id = value["run_id"].as_str().unwrap_or("unknown").to_string();
            return poll_sync_progress(
                &cfg.server_url,
                &run_id,
                timeout_ms,
                poll_interval,
                "同步标的池",
            );
        }
        let run_id = value["run_id"].as_str().unwrap_or("unknown");
        eprintln!("标的池同步任务已提交，服务端后台执行完成后才会写入 quant/config/universes/ 下的列表与 symbol_names.json。");
        eprintln!("文件落在运行 quant 服务的机器上；若与本地仓库路径不一致，请在服务端设置 HIVEFLOW_QUANT_ROOT 或 HIVEFLOW_ROOT。");
        eprintln!("run_id={run_id}");
        eprintln!("查看进度: hf task progress --run-id {run_id}");
        eprintln!("在本终端等到结束: hf data universe-sync --universe {} --wait（或 hf task progress --run-id {run_id} --watch）", args.universe);
        eprintln!("历史列表: hf task list --days 7 --output table");
        print!("{value}");
        return Ok(());
    }

    print!("{value}");
    Ok(())
}
