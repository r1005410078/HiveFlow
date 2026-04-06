use crate::application::requests::PretradeCheckRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client;
use crate::infrastructure::table_renderer::render_pretrade_check_table;
use serde_json::Value;

const PHASE1_NOTIONAL: f64 = 1_000_000.0;

pub fn handle(args: PretradeCheckRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;

    let opt_out = http_client::post_portfolio_optimize(
        &cfg.server_url,
        &args.as_of,
        cfg.timeout_ms,
    )?;
    let target_weights: Value = opt_out
        .get("data")
        .and_then(|d| d.get("target_weights"))
        .and_then(|tw| {
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

    let out = http_client::post_pretrade_check(
        &cfg.server_url,
        &args.as_of,
        target_weights,
        PHASE1_NOTIONAL,
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_pretrade_check_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for pretrade check: {other} (expected: json|table)"
            )));
        }
    }
    Ok(())
}
