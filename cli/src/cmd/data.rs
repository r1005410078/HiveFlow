use crate::application::requests::{
    DataBarsRequest, DataCoverageRequest, DataMarketQueryRequest, DataSymbolNamesSyncRequest,
    DataSyncCancelRequest, DataSyncRequest, DataSyncRetryFailedRequest, DataUniverseSyncRequest,
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
    /// 仅合并 symbol_names.json（POST /v1/market-data/universes/symbol-names/sync）
    SymbolNamesSync(DataSymbolNamesSyncArgs),
    /// 按时间窗查询 K 线（GET /v1/market-data/bars）；默认 TUI 分页表
    Query(DataMarketQueryArgs),
    Bars(DataBarsArgs),
    /// universe 标的与库内 1d K 线覆盖对比（GET /v1/market-data/coverage）
    Coverage(DataCoverageArgs),
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

const DATA_UNIVERSE_SYNC_LONG_ABOUT: &str = "从数据源拉取标的池并写入 **运行 quant 服务的那台机器** 上的 `quant/config/universes/{universe}.txt`，并合并 `symbol_names.json`。\n\
\n\
有数据库时接口为异步（202）：CLI 默认立即打印含 `run_id` 的 JSON，**文件在后台任务成功后才落盘**；本机若看不到文件，请确认服务端工作目录与 `HIVEFLOW_QUANT_ROOT` / `HIVEFLOW_ROOT`（见服务端环境）是否与本地仓库一致。\n\
加 `--wait` 可在本终端轮询至终态，stdout 会打印最终任务详情（含 `progress.universe_result`）。";

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
#[command(
    about = "同步标的池到服务端配置目录（异步时默认仅提交并返回 run_id）",
    long_about = DATA_UNIVERSE_SYNC_LONG_ABOUT,
    after_long_help = "示例:\n  cargo run -- data universe-sync --universe csi300\n  cargo run -- data universe-sync --universe csi300 --wait\n  hf data universe-sync --universe csi300 --wait --poll-interval-ms 2000\n"
)]
pub struct DataUniverseSyncArgs {
    #[arg(long)]
    pub universe: String,
    #[arg(long, default_value = "akshare")]
    pub provider: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
    /// 在本终端轮询直至任务终态后再打印详情 JSON（含 universe 写盘结果）
    #[arg(long, default_value_t = false)]
    pub wait: bool,
    /// 与 --wait 合用：轮询间隔（毫秒），默认约 1500
    #[arg(long)]
    pub poll_interval_ms: Option<u64>,
}

const DATA_SYMBOL_NAMES_SYNC_LONG: &str = "从 akshare 拉取代码与中文简称，**仅**合并服务端 `quant/config/universes/symbol_names.json`。\n\
不修改各 universe 的 `.txt` 列表；默认拉取 csi300、zz500、all_a（可用多次 `--universe` 指定子集）。\n\
请求在服务端同步执行，数据量大时可能较慢。";

#[derive(Debug, Args)]
#[command(
    about = "仅合并 symbol_names.json（中文简称映射）",
    long_about = DATA_SYMBOL_NAMES_SYNC_LONG,
    after_long_help = "示例:\n  cargo run -- data symbol-names-sync\n  cargo run -- data symbol-names-sync --universe csi300 --universe zz500\n  hf data symbol-names-sync --universe csi300\n"
)]
pub struct DataSymbolNamesSyncArgs {
    /// 可重复指定；省略则由服务端默认处理 csi300、zz500、all_a
    #[arg(long = "universe")]
    pub universes: Vec<String>,
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
#[command(
    about = "查询 universe 与库内日线覆盖（GET /v1/market-data/coverage）",
    after_long_help = "示例:\n  cargo run -- data coverage --universe default --start-date 2025-04-06 --end-date 2026-04-06\n  hf data coverage --universe default --start-date 2025-04-06 --end-date 2026-04-06 --output table\n"
)]
pub struct DataCoverageArgs {
    /// 标的池名称（服务端读取 quant/config/universes/{name}.txt）
    #[arg(long)]
    pub universe: String,
    #[arg(long)]
    pub start_date: String,
    #[arg(long)]
    pub end_date: String,
    /// 窗口内至少需要的 1d K 线条数（默认由服务端设为 1）
    #[arg(long)]
    pub min_bars: Option<i32>,
    #[arg(long, default_value = "json")]
    pub output: String,
    #[arg(long)]
    pub timeout_ms: Option<u64>,
}

const DATA_BARS_EXAMPLES: &str = "\
示例:\n  \
  cargo run -- data bars --symbols 600519.SH --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output json\n  \
  cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table\n  \
  cargo run -- data bars --symbols 600519.SH,000001.SZ --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output tui\n  \
  cargo run -- data bars --universe csi300 --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output tui\n  \
  cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output tui --no-benchmark\n  \
  cargo run -- data bars --symbols 600519.SH --start-date 2026-03-01 --end-date 2026-04-01 --output table --verbose\n  \
  cargo run -- data bars --universe csi300 --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output tui --max-display-points 500\n  \
  hf data bars --symbols 600519.SH --timeframe 1d --start-date 2026-03-01 --end-date 2026-04-01 --output json\n\
\n\
tui 图表：/ 打开标的列表筛选（代码或中文简称子串，实时过滤）；编辑中 Enter 结束编辑，Esc 清空关键词并退出编辑；未编辑时 q/Esc/Enter 退出。\n\
";

#[derive(Debug, Args)]
#[command(
    about = "按显式起止日查询 K 线（GET /v1/market-data/bars）；支持 json/table/tui；标的可与 data query 一样用 --universe",
    after_long_help = DATA_BARS_EXAMPLES
)]
pub struct DataBarsArgs {
    /// 逗号分隔标的，如 600519.SH,000001.SZ
    #[arg(long)]
    pub symbols: Option<String>,
    /// 标的池名称（读 quant/config/universes/{name}.txt），与 --symbols 并集去重
    #[arg(long)]
    pub universe: Option<String>,
    /// K 线周期，如 1m / 1d（默认 1m）
    #[arg(long, default_value = "1m")]
    pub timeframe: String,
    /// 区间起始日 YYYY-MM-DD（与 end-date 同用可固定窗口）
    #[arg(long)]
    pub start_date: Option<String>,
    /// 区间结束日 YYYY-MM-DD
    #[arg(long)]
    pub end_date: Option<String>,
    /// 输出：json | table | tui（默认 json）；交互看图用 tui
    #[arg(long, default_value = "json")]
    pub output: String,
    /// 仅在 --output table 下追加诊断列
    #[arg(long, default_value_t = false)]
    pub verbose: bool,
    /// tui 下不绘制大盘对比线（默认基准 000300.SH）
    #[arg(long, default_value_t = false)]
    pub no_benchmark: bool,
    /// 每标的返回条数上限（查询参数 limit，由服务端截断）
    #[arg(long)]
    pub limit: Option<i32>,
    /// 仅 --output tui：每标的用于绘图的最大 K 线点数；超出则按时间顺序分桶合并 OHLC。`0` 关闭聚合
    #[arg(long, default_value_t = 2000)]
    pub max_display_points: usize,
    /// 覆盖 ~/.hiveflow/config.toml 中的 HTTP 超时（毫秒）
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
            wait: args.wait,
            poll_interval_ms: args.poll_interval_ms,
        }
    }
}

impl From<DataSymbolNamesSyncArgs> for DataSymbolNamesSyncRequest {
    fn from(args: DataSymbolNamesSyncArgs) -> Self {
        Self {
            universes: args.universes,
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
            universe: args.universe,
            timeframe: args.timeframe,
            start_date: args.start_date,
            end_date: args.end_date,
            output: args.output,
            verbose: args.verbose,
            no_benchmark: args.no_benchmark,
            limit: args.limit,
            max_display_points: args.max_display_points,
            timeout_ms: args.timeout_ms,
        }
    }
}

impl From<DataCoverageArgs> for DataCoverageRequest {
    fn from(args: DataCoverageArgs) -> Self {
        Self {
            universe: args.universe,
            start_date: args.start_date,
            end_date: args.end_date,
            min_bars: args.min_bars,
            output: args.output,
            timeout_ms: args.timeout_ms,
        }
    }
}
