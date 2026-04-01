use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct DataArgs {
    #[command(subcommand)]
    pub command: DataSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum DataSubcommand {
    Sync(DataSyncArgs),
    Query(DataQueryArgs),
}

#[derive(Debug, Args)]
pub struct DataSyncArgs {
    #[arg(long)]
    pub days: i32,
    #[arg(long)]
    pub end_date: String,
    #[arg(long, default_value = "1d")]
    pub timeframe: String,
    #[arg(long)]
    pub symbols: Option<String>,
    #[arg(long)]
    pub universe: Option<String>,
    #[arg(long)]
    pub request_id: Option<String>,
}

#[derive(Debug, Args)]
pub struct DataQueryArgs {
    #[arg(long)]
    pub days: i32,
    #[arg(long)]
    pub timeframe: Option<String>,
    #[arg(long)]
    pub symbols: Option<String>,
    #[arg(long)]
    pub status: Option<String>,
    #[arg(long, default_value = "json")]
    pub output: String,
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
}
