use crate::application::requests::FactorOptimizeRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct FactorArgs {
    #[command(subcommand)]
    pub command: FactorSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum FactorSubcommand {
    Optimize(FactorOptimizeArgs),
}

#[derive(Debug, Args)]
pub struct FactorOptimizeArgs {
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    #[arg(long)]
    pub factors: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}

impl From<FactorOptimizeArgs> for FactorOptimizeRequest {
    fn from(args: FactorOptimizeArgs) -> Self {
        let factor_names = args
            .factors
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(ToString::to_string)
            .collect();
        Self {
            start_date: args.start_date,
            end_date: args.end_date,
            factor_names,
            output: args.output,
        }
    }
}
