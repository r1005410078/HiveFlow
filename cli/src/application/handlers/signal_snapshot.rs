use crate::application::requests::SignalSnapshotRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_signal_snapshot_table;

pub fn handle(args: SignalSnapshotRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_signal_snapshot(
        &cfg.server_url,
        &args.as_of,
        &args.universes,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_signal_snapshot_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for signal snapshot: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
