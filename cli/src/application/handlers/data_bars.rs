use crate::application::requests::DataBarsRequest;
use crate::error::AppError;
use crate::infrastructure::chart_renderer::render_sync_runs_chart;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_market_data_bars;
use crate::infrastructure::table_renderer::render_market_data_bars_table;
use crate::infrastructure::tui_renderer::render_sync_runs_tui;

const DEFAULT_BENCHMARK_SYMBOL: &str = "000300.SH";

fn parse_csv(input: Option<&str>) -> Option<Vec<String>> {
    input.map(|raw| {
        raw.split(',')
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect::<Vec<_>>()
    })
}

pub fn first_symbol_from_payload(payload: &serde_json::Value) -> Option<String> {
    payload
        .get("items")
        .and_then(serde_json::Value::as_array)
        .and_then(|items| {
            items.iter().find_map(|item| {
                item.get("symbol")
                    .and_then(serde_json::Value::as_str)
                    .map(|s| s.to_string())
            })
        })
}

pub fn chart_fallback_symbol(
    payload: &serde_json::Value,
    explicit_symbol: Option<&str>,
) -> Option<String> {
    explicit_symbol
        .map(|symbol| symbol.to_string())
        .or_else(|| first_symbol_from_payload(payload))
}

pub fn handle(args: DataBarsRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let symbols = parse_csv(args.symbols.as_deref());
    let benchmark_symbol = if args.no_benchmark {
        None
    } else {
        Some(DEFAULT_BENCHMARK_SYMBOL)
    };

    let out = get_market_data_bars(
        &cfg.server_url,
        symbols.as_deref(),
        Some(args.timeframe.as_str()),
        args.start_date.as_deref(),
        args.end_date.as_deref(),
        args.limit,
        timeout_ms,
    )?;

    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_market_data_bars_table(&out, args.verbose);
            print!("{table}");
        }
        "chart" => {
            let chart_symbol = match symbols.as_ref() {
                Some(list) if list.len() == 1 => Some(list[0].clone()),
                _ => {
                    return Err(AppError::InvalidArgs(
                        "chart output requires exactly one symbol via --symbols (e.g. --symbols 600519.SH)"
                            .to_string(),
                    ));
                }
            };
            match render_sync_runs_chart(
                &out,
                chart_symbol.as_deref().unwrap_or("UNKNOWN"),
                benchmark_symbol,
            ) {
                Ok(chart) => print!("{chart}"),
                Err(reason) => {
                    eprintln!("warning: chart output unavailable ({reason}), fallback to table");
                    let table = render_market_data_bars_table(&out, args.verbose);
                    print!("{table}");
                }
            }
        }
        "tui" => {
            let preferred_symbol = symbols
                .as_ref()
                .and_then(|list| list.first())
                .map(|s| s.as_str());
            match render_sync_runs_tui(&out, preferred_symbol, benchmark_symbol) {
                Ok(()) => {}
                Err(reason) => {
                    let fallback_symbol = chart_fallback_symbol(&out, preferred_symbol);
                    if let Some(symbol) = fallback_symbol {
                        eprintln!("warning: tui output unavailable ({reason}), fallback to chart");
                        match render_sync_runs_chart(&out, &symbol, benchmark_symbol) {
                            Ok(chart) => print!("{chart}"),
                            Err(chart_reason) => {
                                eprintln!(
                                    "warning: chart output unavailable ({chart_reason}), fallback to table"
                                );
                                let table = render_market_data_bars_table(&out, args.verbose);
                                print!("{table}");
                            }
                        }
                    } else {
                        eprintln!(
                            "warning: tui output unavailable ({reason}), fallback to table"
                        );
                        let table = render_market_data_bars_table(&out, args.verbose);
                        print!("{table}");
                    }
                }
            }
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for data bars: {other} (expected: json|table|chart|tui)"
            )));
        }
    }

    Ok(())
}
