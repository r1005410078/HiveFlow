use crate::application::requests::RiskCheckRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_risk_check_table;

pub fn handle(args: RiskCheckRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_risk_check(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_risk_check_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for risk check: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
