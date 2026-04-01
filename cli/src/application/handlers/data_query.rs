use crate::cmd::data::DataQueryArgs;
use crate::error::AppError;
use crate::infrastructure::chart_renderer::render_sync_runs_chart;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_data_sync_runs;
use crate::infrastructure::table_renderer::render_sync_runs_table;
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

pub fn handle(args: DataQueryArgs) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let timeout_ms = args.timeout_ms.unwrap_or(cfg.timeout_ms);
    let symbols = parse_csv(args.symbols.as_deref());
    let benchmark_symbol = if args.no_benchmark {
        None
    } else {
        Some(DEFAULT_BENCHMARK_SYMBOL)
    };
    let single_symbol = symbols.as_ref().and_then(|list| {
        if list.len() == 1 {
            Some(list[0].clone())
        } else {
            None
        }
    });
    let chart_symbol = if args.output == "chart" {
        match symbols.as_ref() {
            Some(list) if list.len() == 1 => Some(list[0].clone()),
            _ => {
                return Err(AppError::InvalidArgs(
                    "chart output requires exactly one symbol via --symbols (e.g. --symbols 600519.SH)"
                        .to_string(),
                ));
            }
        }
    } else {
        None
    };
    let mut query_symbols = symbols.clone();
    if benchmark_symbol.is_some() && matches!(args.output.as_str(), "chart" | "tui") {
        if let Some(sym) = single_symbol.as_deref() {
            if sym != DEFAULT_BENCHMARK_SYMBOL {
                match query_symbols.as_mut() {
                    Some(list) => {
                        if !list.iter().any(|s| s == DEFAULT_BENCHMARK_SYMBOL) {
                            list.push(DEFAULT_BENCHMARK_SYMBOL.to_string());
                        }
                    }
                    None => {
                        query_symbols = Some(vec![
                            sym.to_string(),
                            DEFAULT_BENCHMARK_SYMBOL.to_string(),
                        ]);
                    }
                }
            }
        }
    }
    let out = get_data_sync_runs(
        &cfg.server_url,
        args.days,
        Some(args.timeframe.as_str()),
        query_symbols.as_deref(),
        args.status.as_deref(),
        timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_sync_runs_table(&out, args.verbose);
            print!("{table}");
        }
        "chart" => match render_sync_runs_chart(
            &out,
            chart_symbol.as_deref().unwrap_or("UNKNOWN"),
            benchmark_symbol,
        ) {
            Ok(chart) => print!("{chart}"),
            Err(reason) => {
                eprintln!("warning: chart output unavailable ({reason}), fallback to table");
                let table = render_sync_runs_table(&out, args.verbose);
                print!("{table}");
            }
        },
        "tui" => {
            let preferred_symbol = symbols.as_ref().and_then(|list| list.first()).map(|s| s.as_str());
            match render_sync_runs_tui(&out, preferred_symbol, benchmark_symbol) {
            Ok(()) => {}
            Err(reason) => {
                eprintln!("warning: tui output unavailable ({reason}), fallback to chart");
                let fallback_symbol = symbols
                    .as_ref()
                    .and_then(|list| list.first())
                    .map(|s| s.as_str())
                    .unwrap_or("UNKNOWN");
                match render_sync_runs_chart(&out, fallback_symbol, benchmark_symbol) {
                    Ok(chart) => print!("{chart}"),
                    Err(chart_reason) => {
                        eprintln!(
                            "warning: chart output unavailable ({chart_reason}), fallback to table"
                        );
                        let table = render_sync_runs_table(&out, args.verbose);
                        print!("{table}");
                    }
                }
            }
        }
        },
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value: {other} (expected: json|table|chart|tui)"
            )));
        }
    }
    Ok(())
}
