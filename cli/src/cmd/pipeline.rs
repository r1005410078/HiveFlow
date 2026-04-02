use crate::application::requests::{PipelineCompareRequest, PipelineDailyRequest};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct PipelineArgs {
    #[command(subcommand)]
    pub command: PipelineSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum PipelineSubcommand {
    Daily(DailyArgs),
    Compare(CompareArgs),
}

#[derive(Debug, Args)]
pub struct DailyArgs {
    #[arg(long)]
    pub as_of: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}

#[derive(Debug, Args)]
pub struct CompareArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long, default_value_t = 5)]
    pub top_n: usize,
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

impl From<CompareArgs> for PipelineCompareRequest {
    fn from(args: CompareArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            top_n: args.top_n,
            output: args.output,
        }
    }
}
