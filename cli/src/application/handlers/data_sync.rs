use crate::error::AppError;
use crate::application::requests::DataSyncRequest;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_data_sync;

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
    let out = post_data_sync(
        &cfg.server_url,
        args.days,
        &args.end_date,
        &args.timeframe,
        symbols.as_deref(),
        args.universe.as_deref(),
        args.request_id.as_deref(),
        timeout_ms,
    )?;
    print!("{out}");
    Ok(())
}
