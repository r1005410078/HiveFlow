use crate::application::requests::DataSymbolNamesSyncRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_symbol_names_sync;
use indicatif::{ProgressBar, ProgressStyle};
use std::time::Duration;

pub fn handle(args: DataSymbolNamesSyncRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let pb = ProgressBar::new_spinner();
    pb.set_style(
        ProgressStyle::with_template("{spinner:.green} {msg}")
            .unwrap_or_else(|_| ProgressStyle::default_spinner()),
    );
    let msg = if args.universes.is_empty() {
        "正在合并 symbol_names.json（服务端默认 csi300 / zz500 / all_a，可能较久）…".to_string()
    } else {
        format!(
            "正在合并 symbol_names.json（{}）…",
            args.universes.join(", ")
        )
    };
    pb.set_message(msg);
    pb.enable_steady_tick(Duration::from_millis(120));

    let result = post_symbol_names_sync(
        &cfg.server_url,
        &args.universes,
        &args.provider,
        timeout_ms,
    );
    pb.finish_and_clear();
    let out = result?;

    if out.get("status").and_then(|s| s.as_str()) == Some("partial") {
        eprintln!(
            "部分标的池未拉取成功，见 stdout JSON 的 failed_universes；已成功写入的仍会合并进 symbol_names.json。"
        );
    }
    print!("{out}");
    Ok(())
}
