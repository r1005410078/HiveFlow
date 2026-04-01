use crate::application::handlers::{data_query, data_sync, pipeline_daily};
use crate::cmd::{Cli, Commands};
use crate::cmd::data::DataSubcommand;
use crate::error::AppError;

pub fn run(cli: Cli) -> Result<(), AppError> {
    match cli.command {
        Commands::Pipeline(args) => pipeline_daily::handle(args),
        Commands::Data(args) => match args.command {
            DataSubcommand::Sync(sync_args) => data_sync::handle(sync_args),
            DataSubcommand::Query(query_args) => data_query::handle(query_args),
        },
    }
}
