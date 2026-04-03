use crate::application::requests::{FactorOptimizeRequest, FactorReplayRequest};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct FactorArgs {
    #[command(subcommand)]
    pub command: FactorSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum FactorSubcommand {
    Optimize(FactorOptimizeArgs),
    Replay(FactorReplayArgs),
}

#[derive(Debug, Args)]
pub struct FactorOptimizeArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long)]
    pub factors: String,
    #[arg(long)]
    pub correlation_threshold: Option<f64>,
    #[arg(long, default_value = "json")]
    pub output: String,
}

#[derive(Debug, Args)]
pub struct FactorReplayArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long)]
    pub factors: String,
    #[arg(long)]
    pub correlation_threshold: Option<f64>,
    #[arg(long, default_value = "json")]
    pub output: String,
}

fn parse_factor_names(raw: &str) -> Vec<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(ToString::to_string)
        .collect()
}

impl From<FactorOptimizeArgs> for FactorOptimizeRequest {
    fn from(args: FactorOptimizeArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            factor_names: parse_factor_names(&args.factors),
            correlation_threshold: args.correlation_threshold,
            output: args.output,
        }
    }
}

impl From<FactorReplayArgs> for FactorReplayRequest {
    fn from(args: FactorReplayArgs) -> Self {
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            factor_names: parse_factor_names(&args.factors),
            correlation_threshold: args.correlation_threshold,
            output: args.output,
        }
    }
}
