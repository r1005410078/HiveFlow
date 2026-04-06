use serde_json::Value;

use crate::application::requests::WalkForwardRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_walk_forward_run;

pub fn handle(args: WalkForwardRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);

    let result = post_walk_forward_run(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        args.warm_up_days,
        args.test_window_days,
        args.step_days,
        args.cost_bp,
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
    // Extract data from envelope
    if let Some(data) = v.get("data") {
        if let Some(verdict) = data.get("verdict").and_then(|v| v.as_str()) {
            println!("Walk-Forward Backtest Results");
            println!("=============================");
            println!("Verdict: {}", verdict);
            println!();

            // Extract and display failed gates
            if let Some(gates) = data.get("failed_gates").and_then(|v| v.as_array()) {
                if gates.is_empty() {
                    println!("Failed gates: (none)");
                } else {
                    println!("Failed gates:");
                    for gate in gates {
                        if let Some(gate_str) = gate.as_str() {
                            println!("  - {}", gate_str);
                        }
                    }
                }
                println!();
            }

            // Extract window count
            if let Some(windows) = data.get("windows").and_then(|v| v.as_array()) {
                println!("Windows: {} | {} → {}", windows.len(),
                    data.get("params")
                        .and_then(|p| p.get("start_date"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("?"),
                    data.get("params")
                        .and_then(|p| p.get("end_date"))
                        .and_then(|v| v.as_str())
                        .unwrap_or("?")
                );
                println!();
            }

            // Display aggregate metrics
            if let Some(agg) = data.get("aggregate") {
                println!("Aggregate Metrics (mean / min / max)");
                println!("====================================");

                // Annualized return
                if let Some(ann_return) = agg.get("annualized_return") {
                    let mean = ann_return.get("mean")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:+.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    let min = ann_return.get("min")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:+.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    let max = ann_return.get("max")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:+.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    println!("  Annualized:  {} / {} / {}", mean, min, max);
                }

                // Sharpe ratio
                if let Some(sharpe) = agg.get("sharpe") {
                    let mean = sharpe.get("mean")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.2}", x))
                        .unwrap_or_else(|| "N/A".to_string());
                    let min = sharpe.get("min")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.2}", x))
                        .unwrap_or_else(|| "N/A".to_string());
                    let max = sharpe.get("max")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.2}", x))
                        .unwrap_or_else(|| "N/A".to_string());
                    println!("  Sharpe:       {} / {} / {}", mean, min, max);
                }

                // Max drawdown
                if let Some(max_dd) = agg.get("max_drawdown") {
                    let mean = max_dd.get("mean")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    let min = max_dd.get("min")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    let max = max_dd.get("max")
                        .and_then(|v| v.as_f64())
                        .map(|x| format!("{:.1}%", x * 100.0))
                        .unwrap_or_else(|| "N/A".to_string());
                    println!("  Max Drawdown: {} / {} / {}", mean, min, max);
                }
            }
        }
    }
}
