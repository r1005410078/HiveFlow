use clap::{Args, Subcommand};
use crate::application::requests::PipelineDailyRequest;

#[derive(Debug, Args)]
pub struct PipelineArgs {
    #[command(subcommand)]
    pub command: PipelineSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum PipelineSubcommand {
    Daily(DailyArgs),
}

#[derive(Debug, Args)]
pub struct DailyArgs {
    #[arg(long)]
    pub as_of: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}

impl From<DailyArgs> for PipelineDailyRequest {
    fn from(args: DailyArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
