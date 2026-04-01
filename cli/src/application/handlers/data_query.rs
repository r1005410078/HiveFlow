use crate::cmd::data::DataQueryArgs;
use crate::error::AppError;
use crate::infrastructure::chart_renderer::render_sync_runs_chart;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::get_data_sync_runs;
use crate::infrastructure::table_renderer::render_sync_runs_table;

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
    let symbols = parse_csv(args.symbols.as_deref());
    let out = get_data_sync_runs(
        &cfg.server_url,
        args.days,
        args.timeframe.as_deref(),
        symbols.as_deref(),
        args.status.as_deref(),
        cfg.timeout_ms,
    )?;
    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_sync_runs_table(&out, args.verbose);
            print!("{table}");
        }
        "chart" => match render_sync_runs_chart(&out) {
            Ok(chart) => print!("{chart}"),
            Err(reason) => {
                eprintln!("warning: chart output unavailable ({reason}), fallback to table");
                let table = render_sync_runs_table(&out, args.verbose);
                print!("{table}");
            }
        },
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value: {other} (expected: json|table|chart)"
            )));
        }
    }
    Ok(())
}
