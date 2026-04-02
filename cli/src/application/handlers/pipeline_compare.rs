use crate::application::requests::PipelineCompareRequest;
use crate::error::AppError;
use crate::infrastructure::config_loader::load_default_config;
use crate::infrastructure::http_client::post_pipeline_compare;
use crate::infrastructure::table_renderer::render_pipeline_compare_table;

pub fn handle(args: PipelineCompareRequest) -> Result<(), AppError> {
    let cfg = load_default_config()?;
    let out = post_pipeline_compare(
        &cfg.server_url,
        &args.start_date,
        &args.end_date,
        args.top_n,
        cfg.timeout_ms,
    )?;

    match args.output.as_str() {
        "json" => print!("{out}"),
        "table" => {
            let table = render_pipeline_compare_table(&out);
            print!("{table}");
        }
        other => {
            return Err(AppError::InvalidArgs(format!(
                "unsupported --output value for pipeline compare: {other} (expected: json|table)"
            )));
        }
    }

    Ok(())
}
