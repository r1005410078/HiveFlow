use serde_json::Value;

use crate::application::handlers::data_sync::poll_sync_progress;
use crate::application::requests::TaskProgressRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::{get_market_data_sync_runs, get_sync_run_detail};
use crate::infrastructure::table_renderer::render_sync_run_progress_summary;

fn running_run_ids(list: &Value) -> Vec<String> {
    let Some(items) = list.get("items").and_then(Value::as_array) else {
        return Vec::new();
    };
    items
        .iter()
        .filter(|item| item.get("status").and_then(Value::as_str) == Some("running"))
        .filter_map(|item| item.get("run_id").and_then(Value::as_str).map(String::from))
        .collect()
}

pub fn handle(args: TaskProgressRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let run_id = if let Some(ref id) = args.run_id {
        id.clone()
    } else {
        let list = get_market_data_sync_runs(
            &cfg.server_url,
            args.days,
            args.timeframe.as_deref(),
            Some("running"),
            None,
            Some(args.limit),
            timeout_ms,
        )?;
        let ids = running_run_ids(&list);
        match ids.len() {
            0 => {
                eprintln!(
                    "当前无运行中的同步任务（已查近期 --days {}，status=running）。",
                    args.days
                );
                return Ok(());
            }
            1 => ids[0].clone(),
            _ => {
                return Err(AppError::InvalidArgs(format!(
                    "发现多条 running 任务，请指定 --run-id。run_id: {}",
                    ids.join(", ")
                )));
            }
        }
    };

    if args.watch {
        let poll_interval = args.poll_interval_ms.unwrap_or(1500);
        return poll_sync_progress(
            &cfg.server_url,
            &run_id,
            timeout_ms,
            poll_interval,
            "同步任务",
        );
    }

    let detail = get_sync_run_detail(&cfg.server_url, &run_id, timeout_ms)?;
    match args.output.as_str() {
        "json" => print!("{detail}"),
        "table" => {
            let table = render_sync_run_progress_summary(&detail, args.verbose);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output for task progress: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn running_run_ids_filters_and_collects() {
        let list = json!({"items":[
            {"run_id":"a","status":"running"},
            {"run_id":"b","status":"success"},
            {"run_id":"c","status":"running"}
        ]});
        let ids = running_run_ids(&list);
        assert_eq!(ids, vec!["a".to_string(), "c".to_string()]);
    }

    #[test]
    fn running_run_ids_empty_items() {
        let list = json!({"items":[]});
        assert!(running_run_ids(&list).is_empty());
    }
}
