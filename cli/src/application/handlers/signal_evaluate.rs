use crate::application::requests::SignalEvaluateRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_signal_evaluate_table;

pub fn handle(args: SignalEvaluateRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_signal_evaluate(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        args.forward_days,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_signal_evaluate_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for signal evaluate: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
