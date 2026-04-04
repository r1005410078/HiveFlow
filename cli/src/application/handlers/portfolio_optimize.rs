use crate::application::requests::PortfolioOptimizeRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_portfolio_optimize_table;

pub fn handle(args: PortfolioOptimizeRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = http_client::post_portfolio_optimize(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_portfolio_optimize_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for portfolio optimize: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
