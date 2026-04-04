use crate::application::handlers::{
    data_bars, data_market_query, data_sync, data_sync_cancel, data_sync_retry_failed,
    data_universe_sync, factor_optimize, factor_replay, pipeline_compare, pipeline_daily,
    portfolio_optimize, signal_evaluate, signal_snapshot, task_list, task_progress,
};
use crate::application::requests::AppCommand;
use crate::error::AppError;

pub fn run(command: AppCommand) -> Result<(), AppError> {
    match command {
        AppCommand::PipelineDaily(args) => pipeline_daily::handle(args),
        AppCommand::PipelineCompare(args) => pipeline_compare::handle(args),
        AppCommand::FactorOptimize(args) => factor_optimize::handle(args),
        AppCommand::FactorReplay(args) => factor_replay::handle(args),
        AppCommand::DataSync(args) => data_sync::handle(args),
        AppCommand::DataSyncCancel(args) => data_sync_cancel::handle(args),
        AppCommand::DataSyncRetryFailed(args) => data_sync_retry_failed::handle(args),
        AppCommand::DataUniverseSync(args) => data_universe_sync::handle(args),
        AppCommand::TaskList(args) => task_list::handle(args),
        AppCommand::TaskProgress(args) => task_progress::handle(args),
        AppCommand::TaskCancel(args) => data_sync_cancel::handle(args),
        AppCommand::TaskRetryFailed(args) => data_sync_retry_failed::handle(args),
        AppCommand::DataQuery(args) => data_market_query::handle(args),
        AppCommand::DataBars(args) => data_bars::handle(args),
        AppCommand::SignalSnapshot(args) => signal_snapshot::handle(args),
        AppCommand::SignalEvaluate(args) => signal_evaluate::handle(args),
        AppCommand::PortfolioOptimize(args) => portfolio_optimize::handle(args),
    }
}
