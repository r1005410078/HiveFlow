use serde_json::Value;

use crate::application::requests::DataCoverageRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_market_data_coverage;

pub fn handle(args: DataCoverageRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let result = get_market_data_coverage(
        &cfg.server_url,
        &args.universe,
        &args.start_date,
        &args.end_date,
        args.min_bars,
        timeout_ms,
    )?;

    if args.output == "table" {
        print_table(&result);
    } else {
        println!("{}", serde_json::to_string_pretty(&result).unwrap_or_default());
    }
    Ok(())
}

fn print_table(v: &Value) {
    let rate = v["coverage_rate"].as_f64().unwrap_or(0.0) * 100.0;
    println!(
        "Universe: {}  |  {}/{} covered ({:.1}%)",
        v["universe"].as_str().unwrap_or(""),
        v["covered_count"].as_u64().unwrap_or(0),
        v["universe_size"].as_u64().unwrap_or(0),
        rate,
    );
    println!("{:<16} {}", "SYMBOL", "STATUS");
    println!("{}", "-".repeat(28));
    if let Some(arr) = v["covered"].as_array() {
        for sym in arr {
            if let Some(s) = sym.as_str() {
                println!("{:<16} covered", s);
            }
        }
    }
    if let Some(arr) = v["missing"].as_array() {
        for sym in arr {
            if let Some(s) = sym.as_str() {
                println!("{:<16} MISSING", s);
            }
        }
    }
}
