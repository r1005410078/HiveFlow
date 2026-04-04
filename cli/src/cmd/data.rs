use crate::application::requests::{
    DataBarsRequest, DataMarketQueryRequest, DataSyncCancelRequest, DataSyncRequest,
    DataSyncRetryFailedRequest, DataUniverseSyncRequest,
};
use clap::{Args, Subcommand};

/// 市场数据：异步行情同步、任务查询、K 线等（需 quant 服务与 ~/.hiveflow/config.toml）
#[derive(Debug, Args)]
#[command(about = "市场数据子命令")]
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
    /// 按时间窗查询 K 线（GET /v1/market-data/bars）；默认 TUI 分页表
    Query(DataMarketQueryArgs),
    Bars(DataBarsArgs),
}

const DATA_SYNC_LONG_ABOUT: &str = "L1 行情异步同步：服务端后台执行任务。\n\
\n\
默认：提交成功后立即在终端提示「任务已提交」并打印含 run_id 的 JSON，**不**阻塞轮询（避免长时间停在 resolving_symbols 等阶段）。\n\
需要在本终端等到终态时请加 `--wait`；轮询时 Ctrl+C 仅结束本地等待，服务端任务会继续。\n\
若同维度已有运行中任务，接口返回 409，需先 `sync-cancel` 或等待结束。\n\
查看任务列表用 `hf task list`。\n\
stdout 为 JSON（与 CLI 输出合同一致）；提示语在 stderr。";

const DATA_SYNC_AFTER_LONG_HELP: &str = "\
示例:\n  \
  cargo run -- data sync --days 30 --end-date 2026-04-01\n  \
  cargo run -- data sync --days 30 --end-date 2026-04-01 --wait\n  \
  cargo run -- data sync --days 7 --end-date 2026-04-01 --symbols 600519.SH,000001.SZ\n  \
  cargo run -- data sync --days 30 --end-date 2026-04-01 --universe csi300\n  \
  cargo run -- data sync --days 90 --end-date 2026-04-01 --timeframe 1d\n  \
  cargo run -- data sync --days 30 --end-date 2026-04-01 --wait --poll-interval-ms 2000\n  \
  cargo run -- data sync --days 30 --end-date 2026-04-01 --timeout-ms 120000\n  \
  hf data sync --days 30 --end-date 2026-04-01\n\
";

#[derive(Debug, Args)]
#[command(
    about = "异步拉取 K 线并写入库（默认仅提交并返回 run_id）",
    long_about = DATA_SYNC_LONG_ABOUT,
    after_long_help = DATA_SYNC_AFTER_LONG_HELP
)]
pub struct DataSyncArgs {
    /// 回溯自然日天数（与 end-date 一起确定窗口）
    #[arg(long)]
    pub days: i32,
    /// 窗口结束日，格式 YYYY-MM-DD
    #[arg(long)]
    pub end_date: String,
    /// K 线周期，如 1m / 1d
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    /// 逗号分隔标的，如 600519.SH,000001.SZ（与 --universe 二选一场景下按服务端规则）
    #[arg(long)]
    pub symbols: Option<String>,
    /// 使用配置中的标的池名称（如 csi300），与显式 symbols 二选一
    #[arg(long)]
    pub universe: Option<String>,
    /// 幂等/追踪用请求 ID，可选
    #[arg(long)]
    pub request_id: Option<String>,
    /// 覆盖 ~/.hiveflow/config.toml 中的 timeout_ms（毫秒）
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    /// 在本终端轮询直至任务终态（success/failed/cancelled 等）；默认不等待
    #[arg(long, default_value_t = false)]
    pub wait: bool,
    /// 与 --wait 合用：轮询间隔（毫秒），默认约 1500
    #[arg(long)]
    pub poll_interval_ms: Option<u64>,
}

const DATA_SYNC_CANCEL_LONG_ABOUT: &str = "取消指定 run_id 的同步任务（若仍在运行则标记取消；已终态则按服务端语义返回）。";

#[derive(Debug, Args)]
#[command(
    about = "取消正在运行或排队中的同步任务",
    long_about = DATA_SYNC_CANCEL_LONG_ABOUT,
    after_long_help = "示例:\n  cargo run -- data sync-cancel --run-id <run_id>\n  hf data sync-cancel --run-id <run_id>\n"
)]
pub struct DataSyncCancelArgs {
    /// 由 sync 或 task list 返回的任务 run_id
    #[arg(long)]
    pub run_id: String,
    /// HTTP 超时（毫秒）
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

const DATA_SYNC_RETRY_LONG_ABOUT: &str = "基于某次已完成同步的 run_id，仅重试失败标的队列；服务端创建新任务。默认仅提交并打印 JSON；加 `--wait` 在本终端轮询至终态。";

#[derive(Debug, Args)]
#[command(
    about = "对某次同步的失败标的发起重试",
    long_about = DATA_SYNC_RETRY_LONG_ABOUT,
    after_long_help = "示例:\n  cargo run -- data sync-retry-failed --from-run-id <run_id>\n  cargo run -- data sync-retry-failed --from-run-id <run_id> --wait\n"
)]
pub struct DataSyncRetryFailedArgs {
    /// 源同步任务的 run_id（该次任务需已有失败队列记录）
    #[arg(long)]
    pub from_run_id: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    /// 在本终端轮询直至重试任务终态；默认仅提交并打印 JSON
    #[arg(long, default_value_t = false)]
    pub wait: bool,
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

const DATA_MARKET_QUERY_LONG: &str = "按自然日窗口查询 **K 线**（GET /v1/market-data/bars）。\n\
\n\
标的来自 `--symbols` 与 `--universe` 的 **并集去重**（至少其一）。`--universe` 读取仓库 `quant/config/universes/{name}.txt`（需 `HIVEFLOW_ROOT` 或在仓库内执行）。\n\
大标的池会按每批 30 只多次请求后合并；单批失败则整命令失败。\n\
\n\
日期：未指定 `--end-date` 时结束日为今天；`--start-date` 与 `--end-date` 同时给出时忽略 `--days` 窗口推算。";

const DATA_MARKET_QUERY_EXAMPLES: &str = "\
示例:\n  \
  cargo run -- data query --days 7 --symbols 600519.SH --output tui\n  \
  cargo run -- data query --days 14 --universe self_select --timeframe 1d --output json\n  \
  cargo run -- data query --days 7 --symbols 600519.SH --universe csi300 --output table\n  \
  cargo run -- data query --start-date 2026-03-01 --end-date 2026-04-01 --symbols 000001.SZ --output tui\n\
";

#[derive(Debug, Args)]
#[command(
    about = "查询 K 线（默认 TUI 分页；显式区间见 data bars）",
    long_about = DATA_MARKET_QUERY_LONG,
    after_long_help = DATA_MARKET_QUERY_EXAMPLES
)]
pub struct DataMarketQueryArgs {
    /// 回溯自然日天数（与 end-date 推算起点；与 start+end 同时给出时不用于推算）
    #[arg(long)]
    pub days: i32,
    /// 窗口结束日 YYYY-MM-DD；默认今天
    #[arg(long)]
    pub end_date: Option<String>,
    /// 与 end_date 同时指定时固定窗口（需两者都有）
    #[arg(long)]
    pub start_date: Option<String>,
    /// 逗号分隔标的
    #[arg(long)]
    pub symbols: Option<String>,
    /// 标的池名称（读 quant/config/universes/{name}.txt）
    #[arg(long)]
    pub universe: Option<String>,
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    #[arg(long)]
    pub limit: Option<i32>,
    #[arg(long, default_value = "tui")]
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
            wait: args.wait,
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
            wait: args.wait,
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

impl From<DataMarketQueryArgs> for DataMarketQueryRequest {
    fn from(args: DataMarketQueryArgs) -> Self {
        Self {
            days: args.days,
            end_date: args.end_date,
            start_date: args.start_date,
            symbols: args.symbols,
            universe: args.universe,
            timeframe: args.timeframe,
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
