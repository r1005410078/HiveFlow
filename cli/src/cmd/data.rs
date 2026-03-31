use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct DataArgs {
    #[command(subcommand)]
    pub command: DataSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum DataSubcommand {
    Snapshot,
}
