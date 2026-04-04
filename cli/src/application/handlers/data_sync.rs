use crate::application::requests::DataSyncRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::{get_sync_run_detail, post_data_sync};
use indicatif::{ProgressBar, ProgressStyle};
use serde_json::Value;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

fn parse_csv(input: Option<&str>) -> Option<Vec<String>> {
    input.map(|raw| {
        raw.split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
    })
}

/// True when the server accepted an async job (202-style body with `run_id` + `running`).
pub(crate) fn sync_run_async_accepted(value: &Value) -> bool {
    value.get("run_id").is_some()
        && value.get("status").and_then(|s| s.as_str()) == Some("running")
}

pub fn handle(args: DataSyncRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let poll_interval = args.poll_interval_ms.unwrap_or(1500);
    let symbols = parse_csv(args.symbols.as_deref());

    let result = post_data_sync(
        &cfg.server_url,
        args.days,
        &args.end_date,
        &args.timeframe,
        symbols.as_deref(),
        args.universe.as_deref(),
        args.request_id.as_deref(),
        timeout_ms,
    );

    match result {
        Ok(value) => {
            if sync_run_async_accepted(&value) {
                if args.wait {
                    let run_id = value["run_id"].as_str().unwrap_or("unknown").to_string();
                    return poll_sync_progress(
                        &cfg.server_url,
                        &run_id,
                        timeout_ms,
                        poll_interval,
                        "同步行情中",
                    );
                }
                let run_id = value["run_id"].as_str().unwrap_or("unknown");
                eprintln!("任务已提交，服务端后台执行中。");
                eprintln!("run_id={run_id}");
                eprintln!("查看进度: hf task progress --run-id {run_id}（或 hf task progress 自动发现）");
                eprintln!("在本终端等到结束: hf task progress --run-id {run_id} --watch（或提交时加 --wait）");
                eprintln!("历史列表: hf task list --days 7 --output table");
                print!("{value}");
                return Ok(());
            }
            print!("{value}");
            Ok(())
        }
        Err(AppError::Upstream(409, ref body)) => {
            let running_id = body["running_run_id"].as_str().unwrap_or("unknown");
            eprintln!("同步任务已在运行中 (run_id={running_id})");
            eprintln!(
                "使用 `hf data sync-cancel --run-id {running_id}` 取消当前任务，或等待完成后重试"
            );
            Err(result.unwrap_err())
        }
        Err(e) => Err(e),
    }
}

/// Poll `GET /v1/market-data/sync-runs/{run_id}` until the run reaches a
/// terminal status. Shared by `data_sync` and `data_sync_retry_failed`.
pub(crate) fn poll_sync_progress(
    server_url: &str,
    run_id: &str,
    timeout_ms: u64,
    poll_interval_ms: u64,
    operation_label: &str,
) -> Result<(), AppError> {
    let interrupted = Arc::new(AtomicBool::new(false));
    {
        let flag = interrupted.clone();
        ctrlc::set_handler(move || {
            flag.store(true, Ordering::SeqCst);
        })
        .ok();
    }

    let pb = ProgressBar::new(0);
    let spinner_tpl = format!("{{spinner}} {operation_label}... {{msg}}");
    pb.set_style(
        ProgressStyle::with_template(&spinner_tpl)
            .unwrap_or_else(|_| ProgressStyle::default_spinner()),
    );
    pb.set_message(format!("run_id={run_id}"));
    pb.enable_steady_tick(Duration::from_millis(120));

    let mut switched_to_bar = false;

    loop {
        if interrupted.load(Ordering::SeqCst) {
            pb.finish_and_clear();
            eprintln!("同步仍在服务端继续, run_id={run_id}");
            return Ok(());
        }

        std::thread::sleep(Duration::from_millis(poll_interval_ms));

        let detail = match get_sync_run_detail(server_url, run_id, timeout_ms) {
            Ok(v) => v,
            Err(e) => {
                pb.finish_and_clear();
                eprintln!("轮询失败, 同步仍在服务端继续, run_id={run_id}");
                return Err(e);
            }
        };

        let status = detail["status"].as_str().unwrap_or("");
        match status {
            "success" | "failed" | "cancelled" | "interrupted" => {
                pb.finish_and_clear();
                print!("{detail}");
                return Ok(());
            }
            _ => {
                update_progress(&pb, &detail, &mut switched_to_bar, operation_label);
            }
        }
    }
}

fn update_progress(
    pb: &ProgressBar,
    detail: &Value,
    switched_to_bar: &mut bool,
    operation_label: &str,
) {
    let progress = &detail["progress"];
    let total = progress["total_symbols"].as_u64().unwrap_or(0);
    let completed = progress["completed_symbols"].as_u64().unwrap_or(0);
    let current = progress["current_symbol"].as_str().unwrap_or("");
    let phase = detail["phase"].as_str().unwrap_or("");
    let total_days = progress["total_days"].as_u64().unwrap_or(0);
    let completed_days = progress["completed_days"].as_u64().unwrap_or(0);

    if total > 0 && !*switched_to_bar {
        *switched_to_bar = true;
        pb.set_length(total);
        let bar_tpl = format!("{operation_label} [{{bar:20}}] {{pos}}/{{len}} symbols | {{msg}}");
        pb.set_style(
            ProgressStyle::with_template(&bar_tpl).unwrap_or_else(|_| ProgressStyle::default_bar()),
        );
    }

    if *switched_to_bar {
        pb.set_position(completed);
    }

    let mut parts: Vec<String> = Vec::new();
    if total_days > 0 {
        parts.push(format!("day {completed_days}/{total_days}"));
    }
    if !phase.is_empty() {
        parts.push(phase.to_string());
    }
    if !current.is_empty() {
        parts.push(current.to_string());
    }
    pb.set_message(parts.join(" | "));
}
