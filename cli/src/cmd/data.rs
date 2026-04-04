use crate::application::requests::{
    DataBarsRequest, DataQueryRequest, DataSyncCancelRequest, DataSyncRequest,
    DataSyncRetryFailedRequest, DataUniverseSyncRequest,
};
use clap::{Args, Subcommand};

#[derive(Debug, Args)]
pub struct DataArgs {
    #[command(subcommand)]
    pub command: DataSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum DataSubcommand {
    Sync(DataSyncArgs),
    SyncCancel(DataSyncCancelArgs),
    SyncRetryFailed(DataSyncRetryFailedArgs),
    UniverseSync(DataUniverseSyncArgs),
    Query(DataQueryArgs),
    Bars(DataBarsArgs),
}

#[derive(Debug, Args)]
pub struct DataSyncArgs {
    #[arg(long)]
    pub days: i32,
    #[arg(long)]
    pub end_date: String,
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    #[arg(long)]
    pub symbols: Option<String>,
    #[arg(long)]
    pub universe: Option<String>,
    #[arg(long)]
    pub request_id: Option<String>,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    #[arg(long, default_value_t = false)]
    pub no_wait: bool,
    #[arg(long)]
    pub poll_interval_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct DataSyncCancelArgs {
    #[arg(long)]
    pub run_id: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct DataSyncRetryFailedArgs {
    #[arg(long)]
    pub from_run_id: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    #[arg(long, default_value_t = false)]
    pub no_wait: bool,
}

#[derive(Debug, Args)]
pub struct DataUniverseSyncArgs {
    #[arg(long)]
    pub universe: String,
    #[arg(long, default_value = "akshare")]
    pub provider: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct DataQueryArgs {
    #[arg(long)]
    pub days: i32,
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    #[arg(long)]
    pub status: Option<String>,
    #[arg(long)]
    pub request_id: Option<String>,
    #[arg(long)]
    pub limit: Option<i32>,
    #[arg(long, default_value = "json")]
    pub output: String,
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
pub struct DataBarsArgs {
    #[arg(long)]
    pub symbols: Option<String>,
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    #[arg(long)]
    pub start_date: Option<String>,
    #[arg(long)]
    pub end_date: Option<String>,
    #[arg(long, default_value = "json")]
    pub output: String,
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
    #[arg(long, default_value_t = false)]
    pub no_benchmark: bool,
    #[arg(long)]
    pub limit: Option<i32>,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

impl From<DataSyncArgs> for DataSyncRequest {
    fn from(args: DataSyncArgs) -> Self {
        Self {
            days: args.days,
            end_date: args.end_date,
            timeframe: args.timeframe,
            symbols: args.symbols,
            universe: args.universe,
            request_id: args.request_id,
            timeout_ms: args.timeout_ms,
            no_wait: args.no_wait,
            poll_interval_ms: args.poll_interval_ms,
        }
    }
}

impl From<DataSyncCancelArgs> for DataSyncCancelRequest {
    fn from(args: DataSyncCancelArgs) -> Self {
        Self {
            run_id: args.run_id,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<DataSyncRetryFailedArgs> for DataSyncRetryFailedRequest {
    fn from(args: DataSyncRetryFailedArgs) -> Self {
        Self {
            from_run_id: args.from_run_id,
            timeout_ms: args.timeout_ms,
            no_wait: args.no_wait,
        }
    }
}

impl From<DataUniverseSyncArgs> for DataUniverseSyncRequest {
    fn from(args: DataUniverseSyncArgs) -> Self {
        Self {
            universe: args.universe,
            provider: args.provider,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<DataQueryArgs> for DataQueryRequest {
    fn from(args: DataQueryArgs) -> Self {
        Self {
            days: args.days,
            timeframe: args.timeframe,
            status: args.status,
            request_id: args.request_id,
            limit: args.limit,
            output: args.output,
            verbose: args.verbose,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<DataBarsArgs> for DataBarsRequest {
    fn from(args: DataBarsArgs) -> Self {
        Self {
            symbols: args.symbols,
            timeframe: args.timeframe,
            start_date: args.start_date,
            end_date: args.end_date,
            output: args.output,
            verbose: args.verbose,
            no_benchmark: args.no_benchmark,
            limit: args.limit,
            timeout_ms: args.timeout_ms,
        }
    }
}
