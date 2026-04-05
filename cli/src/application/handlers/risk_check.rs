use crate::application::requests::RiskCheckRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_risk_check_table;
use serde_json::Value;

pub fn handle(args: RiskCheckRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;

    // Step 1: get target weights from L4 portfolio optimize
    let opt_out = http_client::post_portfolio_optimize(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    let target_weights: Value = opt_out
        .get("data")
        .and_then(|d| d.get("target_weights"))
        .and_then(|tw| {
            // Convert list [{symbol, weight, ...}] → {symbol: weight}
            tw.as_array().map(|arr| {
                let map: serde_json::Map<String, Value> = arr
                    .iter()
                    .filter_map(|row| {
                        let sym = row.get("symbol")?.as_str()?.to_string();
                        let w = row.get("weight")?.clone();
                        Some((sym, w))
                    })
                    .collect();
                Value::Object(map)
            })
        })
        .unwrap_or_else(|| Value::Object(serde_json::Map::new()));

    // Step 2: call L5 risk check with those weights
    let out = http_client::post_risk_check(
        &cfg.server_url,
        &args.as_of,
        target_weights,
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
