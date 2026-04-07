use crate::application::requests::{PipelineCompareRequest, PipelineDailyRequest};
use chrono::Local;
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
    /// 交易日 (YYYY-MM-DD)；省略则使用本机当天日期
    #[arg(long)]
    pub as_of: Option<String>,
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
        let as_of = args
            .as_of
            .unwrap_or_else(|| Local::now().format("%Y-%m-%d").to_string());
        Self {
            as_of,
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
