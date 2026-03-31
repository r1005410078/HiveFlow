use clap::{Args, Subcommand};

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
}
