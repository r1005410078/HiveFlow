pub mod data;
pub mod pipeline;

use crate::application::requests::AppCommand;
use clap::{Parser, Subcommand};

#[derive(Debug, Parser)]
#[command(name = "hf")]
#[command(about = "HiveFlow CLI")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Debug, Subcommand)]
pub enum Commands {
    Pipeline(pipeline::PipelineArgs),
    Data(data::DataArgs),
}

impl From<Cli> for AppCommand {
    fn from(cli: Cli) -> Self {
        match cli.command {
            Commands::Pipeline(args) => match args.command {
                pipeline::PipelineSubcommand::Daily(daily) => {
                    AppCommand::PipelineDaily(daily.into())
                }
                pipeline::PipelineSubcommand::Compare(compare) => {
                    AppCommand::PipelineCompare(compare.into())
                }
            },
            Commands::Data(args) => match args.command {
                data::DataSubcommand::Sync(sync_args) => AppCommand::DataSync(sync_args.into()),
                data::DataSubcommand::Query(query_args) => AppCommand::DataQuery(query_args.into()),
                data::DataSubcommand::Bars(bars_args) => AppCommand::DataBars(bars_args.into()),
            },
        }
    }
}
