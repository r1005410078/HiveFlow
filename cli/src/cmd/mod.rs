pub mod data;
pub mod factor;
pub mod pipeline;
pub mod signal;

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
    Factor(factor::FactorArgs),
    Data(data::DataArgs),
    /// L3 信号工程：因子截面 → signal_matrix（需 quant 服务与 ~/.hiveflow/config.toml）
    Signal(signal::SignalArgs),
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
            Commands::Factor(args) => match args.command {
                factor::FactorSubcommand::Optimize(optimize) => {
                    AppCommand::FactorOptimize(optimize.into())
                }
                factor::FactorSubcommand::Replay(replay) => AppCommand::FactorReplay(replay.into()),
            },
            Commands::Data(args) => match args.command {
                data::DataSubcommand::Sync(sync_args) => AppCommand::DataSync(sync_args.into()),
                data::DataSubcommand::SyncCancel(args) => AppCommand::DataSyncCancel(args.into()),
                data::DataSubcommand::SyncRetryFailed(args) => {
                    AppCommand::DataSyncRetryFailed(args.into())
                }
                data::DataSubcommand::UniverseSync(sync_args) => {
                    AppCommand::DataUniverseSync(sync_args.into())
                }
                data::DataSubcommand::Query(query_args) => AppCommand::DataQuery(query_args.into()),
                data::DataSubcommand::Bars(bars_args) => AppCommand::DataBars(bars_args.into()),
            },
            Commands::Signal(args) => match args.command {
                signal::SignalSubcommand::Snapshot(snapshot) => {
                    AppCommand::SignalSnapshot(snapshot.into())
                }
                signal::SignalSubcommand::Evaluate(evaluate) => {
                    AppCommand::SignalEvaluate(evaluate.into())
                }
            },
        }
    }
}
