use crate::application::requests::SignalSnapshotRequest;
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct SignalArgs {
    #[command(subcommand)]
    pub command: SignalSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum SignalSubcommand {
    Snapshot(SnapshotArgs),
}

#[derive(Debug, Args)]
pub struct SnapshotArgs {
    #[arg(long)]
    pub as_of: String,
    #[arg(long, default_value = "json")]
    pub output: String,
}

impl From<SnapshotArgs> for SignalSnapshotRequest {
    fn from(args: SnapshotArgs) -> Self {
        Self {
            as_of: args.as_of,
            output: args.output,
        }
    }
}
