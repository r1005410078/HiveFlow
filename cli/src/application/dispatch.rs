use crate::application::handlers::{data_bars, data_query, data_sync, pipeline_daily};
use crate::application::requests::AppCommand;
use crate::error::AppError;

pub fn run(command: AppCommand) -> Result<(), AppError> {
    match command {
        AppCommand::PipelineDaily(args) => pipeline_daily::handle(args),
        AppCommand::DataSync(args) => data_sync::handle(args),
        AppCommand::DataQuery(args) => data_query::handle(args),
        AppCommand::DataBars(args) => data_bars::handle(args),
    }
}
