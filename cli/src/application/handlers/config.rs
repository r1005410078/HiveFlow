use crate::application::requests::{ConfigGetRequest, ConfigListRequest, ConfigSnapshotRequest};
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::{
    get_experiment_config_detail, get_experiment_config_list, post_experiment_config_snapshot,
};
use crate::infrastructure::table_renderer::{
    render_experiment_config_get_table, render_experiment_config_list_table,
    render_experiment_config_snapshot_table,
};

pub fn handle_snapshot(args: ConfigSnapshotRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = post_experiment_config_snapshot(&cfg.server_url, &args.note, timeout_ms)?;
    match args.output.as_str() {
        "json" => println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default()),
        "table" => print!("{}", render_experiment_config_snapshot_table(&out)),
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output for config snapshot: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}

pub fn handle_list(args: ConfigListRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let layer_ref = args.layer.as_deref();
    let out = get_experiment_config_list(
        &cfg.server_url,
        layer_ref,
        args.limit,
        timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default()),
        "table" => print!("{}", render_experiment_config_list_table(&out)),
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output for config list: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}

pub fn handle_get(args: ConfigGetRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let out = get_experiment_config_detail(&cfg.server_url, &args.config_id, timeout_ms)?;
    match args.output.as_str() {
        "json" => println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default()),
        "table" => {
            if out.get("status").and_then(|s| s.as_str()) == Some("error") {
                println!("{}", serde_json::to_string_pretty(&out).unwrap_or_default());
            } else {
                print!("{}", render_experiment_config_get_table(&out));
            }
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output for config get: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
