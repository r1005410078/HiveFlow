use crate::application::requests::FactorOptimizeRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_factor_optimize;
use crate::infrastructure::table_renderer::render_factor_optimize_table;

pub fn handle(args: FactorOptimizeRequest) -> Result<(), AppError> {
    if args.factor_names.is_empty() {
        return Err(AppError::InvalidArgs(
            "--factors must include at least one factor name".to_string(),
        ));
    }

    let cfg = load_default_config()?;
    let out = post_factor_optimize(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        &args.factor_names,
        args.correlation_threshold,
        cfg.timeout_ms,
    )?;

    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_factor_optimize_table(&out)?;
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for factor optimize: {other} (expected: json|table)"
            )));
        }
    }

    Ok(())
}
