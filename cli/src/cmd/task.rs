use crate::application::requests::{
    DataSyncCancelRequest, DataSyncRetryFailedRequest, TaskListRequest, TaskProgressRequest,
};
use clap::{Args, Subcommand};

/// 异步任务：同步作业列表、取消、失败重试等（需 quant 服务与 ~/.hiveflow/config.toml）
#[derive(Debug, Args)]
#[command(about = "任务子命令（同步 run 等）")]
pub struct TaskArgs {
    #[command(subcommand)]
    pub command: TaskSubcommand,
}

#[derive(Debug, Subcommand)]
pub enum TaskSubcommand {
    /// 列出近期行情同步任务（GET /v1/market-data/sync-runs）
    #[command(visible_alias = "sync-runs")]
    List(TaskListArgs),
    /// 查看运行中任务的当前进度（默认识别唯一 running run，或 `--run-id`）
    #[command(visible_alias = "status")]
    Progress(TaskProgressArgs),
    /// 取消正在运行或排队中的同步任务（同 `hf data sync-cancel`）
    #[command(visible_alias = "sync-cancel")]
    Cancel(TaskCancelArgs),
    /// 对某次同步的失败标的发起重试（同 `hf data sync-retry-failed`）
    #[command(visible_alias = "sync-retry-failed")]
    RetryFailed(TaskRetryFailedArgs),
}

#[derive(Debug, Args)]
#[command(
    about = "列出近期同步任务（非 K 线）",
    long_about = "查询近期行情同步任务（run_id、状态等）。查 K 线请用 `hf data query` 或 `hf data bars`。",
    after_long_help = "示例:\n  hf task list --days 7 --output table\n  hf task list --days 30 --output json\n"
)]
pub struct TaskListArgs {
    #[arg(long)]
    pub days: i32,
    #[arg(long, default_value = "15m")]
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
#[command(
    about = "查看运行中同步任务进度",
    long_about = "默认查询近期 `status=running` 的任务：恰有一条则展示进度；无则提示；多条时需指定 `--run-id`。加 `--watch` 在本终端轮询直至终态（同 `hf data sync --wait`）。",
    after_long_help = "示例:\n  hf task progress\n  hf task progress --run-id <run_id>\n  hf task progress --watch\n  hf task progress --output json\n"
)]
pub struct TaskProgressArgs {
    /// 跳过自动发现，直接查看该 run
    #[arg(long)]
    pub run_id: Option<String>,
    /// 与列表接口一致：向前查找 running 任务的天数窗口
    #[arg(long, default_value_t = 7)]
    pub days: i32,
    #[arg(long)]
    pub timeframe: Option<String>,
    /// 自动发现时最多取几条 running（防异常多条）
    #[arg(long, default_value_t = 5)]
    pub limit: i32,
    #[arg(long, default_value = "table")]
    pub output: String,
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    /// 轮询直至 success/failed/cancelled/interrupted（`--poll-interval-ms` 仅与此合用）
    #[arg(long, default_value_t = false)]
    pub watch: bool,
    #[arg(long)]
    pub poll_interval_ms: Option<u64>,
}

#[derive(Debug, Args)]
#[command(about = "取消同步任务")]
pub struct TaskCancelArgs {
    #[arg(long)]
    pub run_id: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

#[derive(Debug, Args)]
#[command(about = "重试同步失败标的")]
pub struct TaskRetryFailedArgs {
    #[arg(long)]
    pub from_run_id: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    #[arg(long, default_value_t = false)]
    pub wait: bool,
}

impl From<TaskListArgs> for TaskListRequest {
    fn from(args: TaskListArgs) -> Self {
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

impl From<TaskProgressArgs> for TaskProgressRequest {
    fn from(args: TaskProgressArgs) -> Self {
        Self {
            run_id: args.run_id,
            days: args.days,
            timeframe: args.timeframe,
            limit: args.limit,
            output: args.output,
            verbose: args.verbose,
            timeout_ms: args.timeout_ms,
            watch: args.watch,
            poll_interval_ms: args.poll_interval_ms,
        }
    }
}

impl From<TaskCancelArgs> for DataSyncCancelRequest {
    fn from(args: TaskCancelArgs) -> Self {
        Self {
            run_id: args.run_id,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<TaskRetryFailedArgs> for DataSyncRetryFailedRequest {
    fn from(args: TaskRetryFailedArgs) -> Self {
        Self {
            from_run_id: args.from_run_id,
            timeout_ms: args.timeout_ms,
            wait: args.wait,
        }
    }
}
