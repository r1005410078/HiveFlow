use crate::application::requests::DataSyncRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_data_sync;
use indicatif::{ProgressBar, ProgressStyle};
use std::time::Duration;

fn parse_csv(input: Option<&str>) -> Option<Vec<String>> {
    input.map(|raw| {
        raw.split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
    })
}

pub fn handle(args: DataSyncRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let symbols = parse_csv(args.symbols.as_deref());
    let target_scope = if let Some(u) = args.universe.as_deref() {
        format!("universe={u}")
    } else if let Some(s) = symbols.as_ref() {
        format!("symbols={}", s.len())
    } else {
        "scope=default".to_string()
    };
    let pb = ProgressBar::new_spinner();
    pb.set_style(
        ProgressStyle::with_template("{spinner} 同步行情中... {msg}")
            .unwrap_or_else(|_| ProgressStyle::default_spinner()),
    );
    pb.set_message(format!(
        "days={} timeframe={} {}",
        args.days, args.timeframe, target_scope
    ));
    pb.enable_steady_tick(Duration::from_millis(120));

    let out = post_data_sync(
        &cfg.server_url,
        args.days,
        &args.end_date,
        &args.timeframe,
        symbols.as_deref(),
        args.universe.as_deref(),
        args.request_id.as_deref(),
        timeout_ms,
    );
    pb.finish_and_clear();
    let out = out?;
    print!("{out}");
    Ok(())
}
